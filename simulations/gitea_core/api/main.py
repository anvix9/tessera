"""
Gitea — Self-hosted Git Service — Core API Replica
Source: https://github.com/go-gitea/gitea
Stack: Go, Vue.js frontend
Pattern: /api/v1/ prefix, token auth, Git hosting
Key resources: repos, issues, users, orgs, pulls, branches, labels, milestones
Endpoints: 42 (core subset from 338 total)
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Header, Query
from typing import Optional
import uuid, random, hashlib, jwt
from datetime import datetime, timedelta

JWT_SECRET = "gitea-secret"
USERS={}; REPOS={}; ISSUES={}; ORGS={}; LABELS={}; MILESTONES={}
COMMENTS={}; PULLS={}; BRANCHES={}; EMAIL_INDEX={}

def _hash(pw): return hashlib.sha256(f"gt-{pw}".encode()).hexdigest()
def _token(u): return jwt.encode({"sub":u["id"],"exp":datetime.utcnow()+timedelta(hours=24)},JWT_SECRET)
def _auth(authorization:Optional[str]=Header(None)):
    if not authorization: raise HTTPException(401)
    try:
        t=authorization.replace("Bearer ","").replace("token ","")
        p=jwt.decode(t,JWT_SECRET,algorithms=["HS256"])
        return USERS.get(p["sub"])
    except: raise HTTPException(401)
def _optauth(authorization:Optional[str]=Header(None)):
    try: return _auth(authorization)
    except: return None

def seed():
    for uname,email,pw,admin in [("admin","admin@gitea.local","admin123",True),
                                   ("dev","dev@gitea.local","dev123",False),
                                   ("contributor","contrib@gitea.local","contrib123",False)]:
        uid=f"u_{uuid.uuid4().hex[:8]}"
        USERS[uid]={"id":uid,"login":uname,"email":email,"password_hash":_hash(pw),
                    "full_name":uname.title(),"avatar_url":f"/avatars/{uname}","is_admin":admin,
                    "followers_count":random.randint(0,100),"following_count":random.randint(0,50),
                    "starred_repos_count":random.randint(0,20)}
        EMAIL_INDEX[email]=uid

    admin_id=[u for u in USERS.values() if u["login"]=="admin"][0]["id"]
    dev_id=[u for u in USERS.values() if u["login"]=="dev"][0]["id"]

    # Repos
    repos=[("admin/webapp","Main web application",["go","docker"],"admin",False),
           ("admin/docs","Documentation site",["markdown"],"admin",False),
           ("dev/cli-tool","Command line utility",["python","cli"],"dev",False),
           ("dev/api-client","API client library",["typescript"],"dev",False),
           ("admin/private-repo","Internal tools",["go"],"admin",True)]
    for full_name,desc,topics,owner,private in repos:
        rid=f"repo_{uuid.uuid4().hex[:6]}"
        REPOS[rid]={"id":rid,"name":full_name.split("/")[1],"full_name":full_name,"owner":{"login":owner},
                    "description":desc,"private":private,"fork":False,
                    "stars_count":random.randint(0,500),"forks_count":random.randint(0,50),
                    "open_issues_count":random.randint(0,30),"topics":topics,
                    "default_branch":"main","created_at":datetime.utcnow().isoformat()}
        # Branches
        for branch in ["main","develop","feature/auth"]:
            BRANCHES[f"{rid}_{branch}"]={"name":branch,"commit":{"id":uuid.uuid4().hex[:40]}}
        # Labels
        for j,lbl in enumerate(["bug","enhancement","documentation","help wanted"]):
            LABELS[f"{rid}_lbl_{j}"]={"id":j+1,"name":lbl,"color":"#"+f"{random.randint(0,0xFFFFFF):06x}",
                                       "description":f"{lbl} label","repo_id":rid}
        # Milestones
        MILESTONES[f"{rid}_ms1"]={"id":1,"title":"v1.0","state":"open","repo_id":rid}

    # Issues
    for i in range(10):
        iid=f"issue_{i+1}"
        rid=list(REPOS.keys())[i%len(REPOS)]
        ISSUES[iid]={"id":iid,"number":i+1,"title":f"Issue #{i+1}: Something to fix",
                     "body":"Detailed description here","state":["open","closed"][i%3==0],
                     "labels":[{"name":"bug"}] if i%2==0 else [],
                     "user":{"login":["admin","dev","contributor"][i%3]},
                     "repo_id":rid,"comments":random.randint(0,10),
                     "created_at":datetime.utcnow().isoformat()}
        # Comments on issues
        for j in range(random.randint(1,3)):
            cid=f"cmt_{i}_{j}"
            COMMENTS[cid]={"id":cid,"body":f"Comment {j+1} on issue {i+1}","issue_id":iid,
                           "user":{"login":["admin","dev"][j%2]},"created_at":datetime.utcnow().isoformat()}

    # Pull Requests (as special issues)
    for i in range(4):
        pid=f"pr_{i+1}"
        rid=list(REPOS.keys())[i%len(REPOS)]
        PULLS[pid]={"id":pid,"number":100+i,"title":f"PR: Feature {i+1}","body":"Changes...",
                    "state":"open","head":{"label":"feature","ref":"feature/auth"},
                    "base":{"label":"main","ref":"main"},"mergeable":True,
                    "user":{"login":["dev","contributor"][i%2]},"repo_id":rid}

    # Orgs
    ORGS["org_1"]={"id":"org_1","username":"myorg","full_name":"My Organization",
                    "description":"Open source org","visibility":"public",
                    "members_count":3,"repos_count":2}

@asynccontextmanager
async def lifespan(app): seed(); yield
app = FastAPI(title="Gitea", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

# === Misc (3) ===
@app.get("/api/v1/version")
def version(): return {"version":"1.22.0"}
@app.get("/api/v1/settings/api")
def api_settings(): return {"max_response_items":50}
@app.get("/api/v1/settings/repository")
def repo_settings(): return {"default_branch":"main"}

# === Users (7) ===
@app.get("/api/v1/users/search")
def search_users(q:str=Query("")): return {"data":[u for u in USERS.values() if q.lower() in u["login"]],"ok":True}
@app.get("/api/v1/users/{username}")
def get_user(username:str):
    for u in USERS.values():
        if u["login"]==username: return u
    raise HTTPException(404)
@app.get("/api/v1/users/{username}/repos")
def user_repos(username:str): return [r for r in REPOS.values() if r["owner"]["login"]==username and not r["private"]]
@app.get("/api/v1/users/{username}/followers")
def user_followers(username:str): return []
@app.get("/api/v1/users/{username}/following")
def user_following(username:str): return []
@app.get("/api/v1/users/{username}/starred")
def user_starred(username:str): return []
@app.get("/api/v1/user")
def get_authenticated_user(u=Depends(_auth)): return u

# === Repos (8) ===
@app.get("/api/v1/repos/search")
def search_repos(q:str=Query("")): return {"data":[r for r in REPOS.values() if q.lower() in r["full_name"] and not r["private"]],"ok":True}
@app.get("/api/v1/repos/{owner}/{repo}")
def get_repo(owner:str,repo:str):
    for r in REPOS.values():
        if r["full_name"]==f"{owner}/{repo}": return r
    raise HTTPException(404)
@app.post("/api/v1/user/repos")
def create_repo(u=Depends(_auth)): return {"id":f"repo_{uuid.uuid4().hex[:6]}","name":"new-repo"}
@app.delete("/api/v1/repos/{owner}/{repo}")
def delete_repo(owner:str,repo:str,u=Depends(_auth)): return {}
@app.get("/api/v1/repos/{owner}/{repo}/branches")
def list_branches(owner:str,repo:str):
    rid=None
    for r in REPOS.values():
        if r["full_name"]==f"{owner}/{repo}": rid=r["id"]; break
    return [b for k,b in BRANCHES.items() if k.startswith(rid or "")]
@app.get("/api/v1/repos/{owner}/{repo}/topics")
def list_topics(owner:str,repo:str):
    for r in REPOS.values():
        if r["full_name"]==f"{owner}/{repo}": return {"topics":r["topics"]}
    raise HTTPException(404)
@app.get("/api/v1/repos/{owner}/{repo}/labels")
def list_labels(owner:str,repo:str):
    rid=None
    for r in REPOS.values():
        if r["full_name"]==f"{owner}/{repo}": rid=r["id"]; break
    return [l for k,l in LABELS.items() if k.startswith(rid or "")]
@app.get("/api/v1/repos/{owner}/{repo}/milestones")
def list_milestones(owner:str,repo:str):
    rid=None
    for r in REPOS.values():
        if r["full_name"]==f"{owner}/{repo}": rid=r["id"]; break
    return [m for k,m in MILESTONES.items() if k.startswith(rid or "")]

# === Issues (8) ===
@app.get("/api/v1/repos/{owner}/{repo}/issues")
def list_issues(owner:str,repo:str,state:Optional[str]=Query(None)):
    rid=None
    for r in REPOS.values():
        if r["full_name"]==f"{owner}/{repo}": rid=r["id"]; break
    items=[i for i in ISSUES.values() if i["repo_id"]==rid]
    if state: items=[i for i in items if i["state"]==state]
    return items
@app.get("/api/v1/repos/{owner}/{repo}/issues/{index}")
def get_issue(owner:str,repo:str,index:int):
    for i in ISSUES.values():
        if i["number"]==index: return i
    raise HTTPException(404)
@app.post("/api/v1/repos/{owner}/{repo}/issues")
def create_issue(owner:str,repo:str,u=Depends(_auth)): return {"id":f"issue_{uuid.uuid4().hex[:6]}","number":999}
@app.patch("/api/v1/repos/{owner}/{repo}/issues/{index}")
def update_issue(owner:str,repo:str,index:int,u=Depends(_auth)): return {}
@app.get("/api/v1/repos/{owner}/{repo}/issues/{index}/comments")
def issue_comments(owner:str,repo:str,index:int):
    iid=None
    for i in ISSUES.values():
        if i["number"]==index: iid=i["id"]; break
    return [c for c in COMMENTS.values() if c.get("issue_id")==iid]
@app.post("/api/v1/repos/{owner}/{repo}/issues/{index}/comments")
def add_issue_comment(owner:str,repo:str,index:int,u=Depends(_auth)): return {"id":f"cmt_{uuid.uuid4().hex[:6]}"}
@app.get("/api/v1/repos/{owner}/{repo}/issues/{index}/labels")
def issue_labels(owner:str,repo:str,index:int): return [{"name":"bug"}]
@app.post("/api/v1/repos/{owner}/{repo}/issues/{index}/labels")
def add_issue_label(owner:str,repo:str,index:int,u=Depends(_auth)): return [{"name":"new-label"}]

# === Pull Requests (4) ===
@app.get("/api/v1/repos/{owner}/{repo}/pulls")
def list_pulls(owner:str,repo:str): return list(PULLS.values())[:5]
@app.get("/api/v1/repos/{owner}/{repo}/pulls/{index}")
def get_pull(owner:str,repo:str,index:int):
    for p in PULLS.values():
        if p["number"]==index: return p
    raise HTTPException(404)
@app.post("/api/v1/repos/{owner}/{repo}/pulls")
def create_pull(owner:str,repo:str,u=Depends(_auth)): return {"id":f"pr_{uuid.uuid4().hex[:6]}","number":200}
@app.patch("/api/v1/repos/{owner}/{repo}/pulls/{index}")
def update_pull(owner:str,repo:str,index:int,u=Depends(_auth)): return {}

# === Orgs (5) ===
@app.get("/api/v1/orgs")
def list_orgs(u=Depends(_auth)): return list(ORGS.values())
@app.get("/api/v1/orgs/{org}")
def get_org(org:str): return ORGS.get("org_1",{})
@app.get("/api/v1/orgs/{org}/repos")
def org_repos(org:str): return list(REPOS.values())[:2]
@app.get("/api/v1/orgs/{org}/members")
def org_members(org:str): return list(USERS.values())[:3]
@app.post("/api/v1/orgs")
def create_org(u=Depends(_auth)): return {"id":"org_new","username":"neworg"}

# === Notifications (2) ===
@app.get("/api/v1/notifications")
def list_notifications(u=Depends(_auth)): return [{"id":"n_1","subject":{"title":"New issue"},"unread":True}]
@app.get("/api/v1/notifications/new")
def new_notifications(u=Depends(_auth)): return {"new":1}

# === Stars (2) ===
@app.get("/api/v1/repos/{owner}/{repo}/stargazers")
def stargazers(owner:str,repo:str): return []
@app.put("/api/v1/user/starred/{owner}/{repo}")
def star_repo(owner:str,repo:str,u=Depends(_auth)): return {}
@app.delete("/api/v1/user/starred/{owner}/{repo}")
def unstar_repo(owner:str,repo:str,u=Depends(_auth)): return {}
