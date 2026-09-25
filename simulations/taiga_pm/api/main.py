"""
Taiga Project Management — Route Replica
Source: https://github.com/taigaio/taiga-back
Stack: Django/Python, Angular frontend
Pattern: /api/v1/ prefix, REST, project management (Kanban/Scrum)
Endpoints: 30
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Header, Query
from typing import Optional
import uuid, random, hashlib, jwt
from datetime import datetime, timedelta

JWT_SECRET = "taiga-pm-secret"
USERS={}; EMAIL_INDEX={}; PROJECTS={}; ISSUES={}; TASKS={}; STORIES={}; EPICS={}
MILESTONES={}; WIKI_PAGES={}; ATTACHMENTS=[]

def _hash(pw): return hashlib.sha256(f"tg-{pw}".encode()).hexdigest()
def _token(u): return jwt.encode({"sub":u["id"],"exp":datetime.utcnow()+timedelta(hours=24)},JWT_SECRET)
def _auth(authorization:Optional[str]=Header(None)):
    if not authorization: raise HTTPException(401)
    try:
        p=jwt.decode(authorization.replace("Bearer ",""),JWT_SECRET,algorithms=["HS256"])
        return USERS.get(p["sub"])
    except: raise HTTPException(401)

def seed():
    for uname,email,pw,name in [("admin","admin@taiga.io","admin123","Admin User"),("dev","dev@taiga.io","dev123","Developer")]:
        uid=f"u_{uuid.uuid4().hex[:8]}"
        USERS[uid]={"id":uid,"username":uname,"email":email,"password_hash":_hash(pw),"full_name":name,
                    "photo":"avatar.jpg","is_active":True,"roles":["admin"] if uname=="admin" else ["developer"]}
        EMAIL_INDEX[email]=uid

    statuses=["New","In Progress","Ready for Test","Done"]
    priorities=["Low","Normal","High","Critical"]
    for i in range(3):
        pid=f"proj_{i+1}"
        PROJECTS[pid]={"id":pid,"name":f"Project {['Alpha','Beta','Gamma'][i]}","slug":f"project-{['alpha','beta','gamma'][i]}",
                       "description":f"Description for project {i+1}","is_private":i>0,
                       "owner":list(USERS.values())[0]["username"],"members":list(USERS.keys()),
                       "total_milestones":2,"total_story_points":random.randint(20,80)}

    for i in range(8):
        iid=f"issue_{i+1}"
        pid=f"proj_{i%3+1}"
        ISSUES[iid]={"id":iid,"ref":i+1,"subject":f"Bug: Something broken #{i+1}","description":"Details...",
                     "project":pid,"status":statuses[i%4],"priority":priorities[i%4],"severity":"Normal",
                     "assigned_to":list(USERS.keys())[i%2],"type":"Bug","created_date":datetime.utcnow().isoformat()}

    for i in range(6):
        tid=f"task_{i+1}"
        TASKS[tid]={"id":tid,"ref":i+100,"subject":f"Task: Do thing #{i+1}","project":f"proj_{i%3+1}",
                    "status":statuses[i%4],"assigned_to":list(USERS.keys())[i%2]}

    for i in range(5):
        sid=f"story_{i+1}"
        STORIES[sid]={"id":sid,"ref":i+200,"subject":f"User Story #{i+1}","project":f"proj_{i%3+1}",
                      "status":statuses[i%4],"points":{"Design":random.randint(1,8),"Dev":random.randint(1,13)}}

    for i in range(2):
        eid=f"epic_{i+1}"
        EPICS[eid]={"id":eid,"ref":i+300,"subject":f"Epic #{i+1}","project":"proj_1"}

    MILESTONES["ms_1"]={"id":"ms_1","name":"Sprint 1","project":"proj_1","estimated_start":"2026-04-01","estimated_finish":"2026-04-14"}
    MILESTONES["ms_2"]={"id":"ms_2","name":"Sprint 2","project":"proj_1","estimated_start":"2026-04-15","estimated_finish":"2026-04-28"}

    WIKI_PAGES["wiki_1"]={"id":"wiki_1","slug":"home","content":"# Welcome","project":"proj_1"}

@asynccontextmanager
async def lifespan(app): seed(); yield
app = FastAPI(title="Taiga", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

# === Auth (2) ===
@app.post("/api/v1/auth")
def login():
    for u in USERS.values():
        return {"auth_token":_token(u),"id":u["id"],"username":u["username"]}
    raise HTTPException(401)
@app.post("/api/v1/auth/register")
def register(): uid=f"u_{uuid.uuid4().hex[:8]}"; return {"auth_token":"...","id":uid}

# === Users (2) ===
@app.get("/api/v1/users")
def list_users(u=Depends(_auth)): return list(USERS.values())
@app.get("/api/v1/users/me")
def get_me(u=Depends(_auth)): return u

# === Projects (4) ===
@app.get("/api/v1/projects")
def list_projects(u=Depends(_auth)): return list(PROJECTS.values())
@app.get("/api/v1/projects/{id}")
def get_project(id:str,u=Depends(_auth)):
    if id not in PROJECTS: raise HTTPException(404)
    return PROJECTS[id]
@app.post("/api/v1/projects")
def create_project(u=Depends(_auth)): return {"id":f"proj_{uuid.uuid4().hex[:6]}","name":"New"}
@app.patch("/api/v1/projects/{id}")
def update_project(id:str,u=Depends(_auth)): return PROJECTS.get(id,{})

# === Issues (4) ===
@app.get("/api/v1/issues")
def list_issues(project:Optional[str]=Query(None),u=Depends(_auth)):
    items=list(ISSUES.values())
    if project: items=[i for i in items if i["project"]==project]
    return items
@app.get("/api/v1/issues/{id}")
def get_issue(id:str,u=Depends(_auth)): return ISSUES.get(id,{})
@app.post("/api/v1/issues")
def create_issue(u=Depends(_auth)): return {"id":f"issue_{uuid.uuid4().hex[:6]}"}
@app.patch("/api/v1/issues/{id}")
def update_issue(id:str,u=Depends(_auth)): return ISSUES.get(id,{})

# === Tasks (4) ===
@app.get("/api/v1/tasks")
def list_tasks(project:Optional[str]=Query(None),u=Depends(_auth)):
    items=list(TASKS.values())
    if project: items=[t for t in items if t["project"]==project]
    return items
@app.get("/api/v1/tasks/{id}")
def get_task(id:str,u=Depends(_auth)): return TASKS.get(id,{})
@app.post("/api/v1/tasks")
def create_task(u=Depends(_auth)): return {"id":f"task_{uuid.uuid4().hex[:6]}"}
@app.patch("/api/v1/tasks/{id}")
def update_task(id:str,u=Depends(_auth)): return TASKS.get(id,{})

# === User Stories (4) ===
@app.get("/api/v1/userstories")
def list_stories(project:Optional[str]=Query(None),u=Depends(_auth)): return list(STORIES.values())
@app.get("/api/v1/userstories/{id}")
def get_story(id:str,u=Depends(_auth)): return STORIES.get(id,{})
@app.post("/api/v1/userstories")
def create_story(u=Depends(_auth)): return {"id":f"story_{uuid.uuid4().hex[:6]}"}
@app.patch("/api/v1/userstories/{id}")
def update_story(id:str,u=Depends(_auth)): return STORIES.get(id,{})

# === Epics (3) ===
@app.get("/api/v1/epics")
def list_epics(u=Depends(_auth)): return list(EPICS.values())
@app.get("/api/v1/epics/{id}")
def get_epic(id:str,u=Depends(_auth)): return EPICS.get(id,{})
@app.post("/api/v1/epics")
def create_epic(u=Depends(_auth)): return {"id":f"epic_{uuid.uuid4().hex[:6]}"}

# === Milestones (3) ===
@app.get("/api/v1/milestones")
def list_milestones(project:Optional[str]=Query(None),u=Depends(_auth)): return list(MILESTONES.values())
@app.get("/api/v1/milestones/{id}")
def get_milestone(id:str,u=Depends(_auth)): return MILESTONES.get(id,{})
@app.post("/api/v1/milestones")
def create_milestone(u=Depends(_auth)): return {"id":f"ms_{uuid.uuid4().hex[:6]}"}

# === Wiki (2) ===
@app.get("/api/v1/wiki")
def list_wiki(u=Depends(_auth)): return list(WIKI_PAGES.values())
@app.get("/api/v1/wiki/{id}")
def get_wiki(id:str,u=Depends(_auth)): return WIKI_PAGES.get(id,{})

# === Resolver (1) ===
@app.get("/api/v1/resolver")
def resolver(project:str=Query(""),us:Optional[int]=Query(None),issue:Optional[int]=Query(None)):
    return {"project":project}
