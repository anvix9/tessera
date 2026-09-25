"""
Forem (dev.to) API — Route Replica
Source: https://github.com/forem/forem
Stack: Ruby on Rails, React frontend
Pattern: /api/ prefix, REST, social blogging
This is the actual API that powers dev.to
Endpoints: 38
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Header, Query
from typing import Optional
import uuid, random, hashlib, jwt
from datetime import datetime, timedelta

JWT_SECRET = "forem-devto-secret"

USERS = {}; EMAIL_INDEX = {}; ARTICLES = {}; COMMENTS = {}; TAGS_LIST = []
ORGS = {}; BADGES = {}; BADGE_ACHIEVEMENTS = []; FOLLOWS = {}; READINGLIST = []
PODCASTS = []; VIDEOS = []

def _hash(pw): return hashlib.sha256(f"fo-{pw}".encode()).hexdigest()
def _token(u): return jwt.encode({"sub":u["id"],"exp":datetime.utcnow()+timedelta(hours=24)},JWT_SECRET)
def _auth(authorization:Optional[str]=Header(None)):
    if not authorization: raise HTTPException(401)
    try:
        p=jwt.decode(authorization.replace("Bearer ","").replace("api-key ",""),JWT_SECRET,algorithms=["HS256"])
        return USERS.get(p["sub"])
    except: raise HTTPException(401)
def _optauth(authorization:Optional[str]=Header(None)):
    try: return _auth(authorization)
    except: return None

def seed():
    for uname,email,pw,name in [("ben","ben@dev.to","dev123","Ben Halpern"),("jess","jess@dev.to","dev456","Jess Lee"),("peter","peter@dev.to","dev789","Peter Kim")]:
        uid=f"u_{uuid.uuid4().hex[:8]}"
        USERS[uid]={"id":uid,"username":uname,"email":email,"password_hash":_hash(pw),"name":name,
                    "summary":f"Co-founder of DEV","profile_image":f"https://dev.to/{uname}.jpg","joined_at":"2024-01-01"}
        EMAIL_INDEX[email]=uid

    arts=[("Building a Modern API with FastAPI","Learn how to build production APIs","programming,python,api","ben"),
          ("Why I Switched from React to Svelte","A developer's journey","javascript,webdev,svelte","jess"),
          ("The Complete Guide to Docker in 2026","Everything you need to know","docker,devops,tutorial","peter"),
          ("Understanding Async/Await in JavaScript","Deep dive into promises","javascript,programming,beginners","ben"),
          ("My First Open Source Contribution","Tips for getting started","opensource,beginners,career","jess"),
          ("Rust vs Go: A 2026 Comparison","Which should you learn?","rust,go,programming","peter"),
          ("CSS Grid: The Ultimate Layout Tool","Master modern CSS","css,webdev,frontend","ben"),
          ("How to Land Your First Dev Job","Career advice for juniors","career,beginners,advice","jess")]
    for i,(title,desc,tags,author) in enumerate(arts):
        aid=f"art_{i+1}"
        uid=[u for u in USERS.values() if u["username"]==author][0]["id"]
        slug=title.lower().replace(" ","-").replace(":","").replace(",","")[:40]+f"-{random.randint(1000,9999)}"
        ARTICLES[aid]={"id":aid,"title":title,"description":desc,"slug":slug,"body_markdown":f"# {title}\n\n{desc}...",
                       "tag_list":tags,"tags":tags.split(","),"user":{"username":author},"user_id":uid,
                       "url":f"https://dev.to/{author}/{slug}","canonical_url":"",
                       "comments_count":random.randint(5,100),"positive_reactions_count":random.randint(10,500),
                       "public_reactions_count":random.randint(10,500),"reading_time_minutes":random.randint(3,15),
                       "published_at":(datetime.utcnow()-timedelta(days=random.randint(1,90))).isoformat(),
                       "created_at":datetime.utcnow().isoformat()}

    TAGS_LIST.extend([{"id":i,"name":t,"bg_color_hex":"#000","text_color_hex":"#fff"}
                      for i,t in enumerate(["python","javascript","webdev","programming","beginners","tutorial",
                                             "react","docker","career","opensource","css","rust","go","devops","api"])])

    ORGS["org_1"]={"id":"org_1","username":"devteam","name":"The DEV Team","summary":"We're the team behind DEV",
                   "profile_image":"https://dev.to/devteam.jpg","slug":"devteam"}

    for i in range(3):
        BADGES[f"badge_{i+1}"]={"id":f"badge_{i+1}","title":f"Badge {i+1}","description":f"Achievement badge {i+1}",
                                 "badge_image":"badge.png"}

    for aid in list(ARTICLES.keys())[:4]:
        for j in range(random.randint(2,5)):
            COMMENTS.setdefault(aid,[]).append({"id":f"c_{uuid.uuid4().hex[:6]}","body_html":f"<p>Great post!</p>",
                                                 "user":{"username":["ben","jess","peter"][j%3]},
                                                 "created_at":datetime.utcnow().isoformat()})

    VIDEOS.extend([{"id":f"v_{i}","title":f"Video {i+1}","user":{"username":"ben"}} for i in range(3)])
    PODCASTS.extend([{"id":f"pe_{i}","title":f"Episode {i+1}","podcast":{"title":"DevPod"}} for i in range(5)])

@asynccontextmanager
async def lifespan(app): seed(); yield
app = FastAPI(title="Forem/dev.to", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

# === Articles (7) ===
@app.get("/api/articles")
def list_articles(tag:Optional[str]=Query(None),username:Optional[str]=Query(None),
                  state:Optional[str]=Query(None),top:Optional[int]=Query(None),
                  page:int=Query(1),per_page:int=Query(30)):
    items=list(ARTICLES.values())
    if tag: items=[a for a in items if tag in a.get("tags",[])]
    if username: items=[a for a in items if a["user"]["username"]==username]
    return items[:per_page]

@app.get("/api/articles/{id}")
def get_article(id:str):
    if id not in ARTICLES: raise HTTPException(404)
    return ARTICLES[id]

@app.post("/api/articles")
def create_article(u=Depends(_auth)):
    aid=f"art_{uuid.uuid4().hex[:6]}"
    ARTICLES[aid]={"id":aid,"title":"New Article","user":{"username":"probe"},"created_at":datetime.utcnow().isoformat()}
    return ARTICLES[aid]

@app.put("/api/articles/{id}")
def update_article(id:str,u=Depends(_auth)):
    if id not in ARTICLES: raise HTTPException(404)
    return ARTICLES[id]

@app.get("/api/articles/search")
def search_articles(q:str=Query("")): return [a for a in ARTICLES.values() if q.lower() in a["title"].lower()][:10]

@app.get("/api/articles/me/{status}")
def my_articles(status:str="published",u=Depends(_auth)):
    return [a for a in ARTICLES.values() if a.get("user_id")==u["id"]]

@app.get("/api/articles/latest")
def latest_articles(): return sorted(ARTICLES.values(),key=lambda a:a.get("published_at",""),reverse=True)[:10]

@app.get("/api/articles/{username}/{slug}")
def get_by_slug(username:str,slug:str):
    for a in ARTICLES.values():
        if a.get("slug","").startswith(slug[:20]): return a
    raise HTTPException(404)

# === Comments (2) ===
@app.get("/api/comments")
def list_comments(a_id:Optional[str]=Query(None)):
    if a_id: return COMMENTS.get(a_id,[])
    all_c=[]
    for cs in COMMENTS.values(): all_c.extend(cs)
    return all_c[:20]

@app.get("/api/comments/{id}")
def get_comment(id:str): return {"id":id,"body_html":"<p>Comment</p>"}

# === Users (2) ===
@app.get("/api/users/{id}")
def get_user(id:str):
    for u in USERS.values():
        if u["id"]==id or u["username"]==id: return u
    raise HTTPException(404)

@app.get("/api/users/me")
def get_me(u=Depends(_auth)): return u

# === Tags (1) ===
@app.get("/api/tags")
def list_tags(): return TAGS_LIST

# === Follows (2) ===
@app.post("/api/follows")
def create_follow(u=Depends(_auth)): return {"result":"followed"}

@app.get("/api/follows/tags")
def followed_tags(u=Depends(_auth)): return []

# === Followers (2) ===
@app.get("/api/followers/users")
def user_followers(u=Depends(_auth)): return []

@app.get("/api/followers/organizations")
def org_followers(u=Depends(_auth)): return []

# === Reading List (1) ===
@app.get("/api/readinglist")
def reading_list(u=Depends(_auth)): return READINGLIST

# === Analytics (4) ===
@app.get("/api/analytics/totals")
def analytics_totals(u=Depends(_auth)): return {"totals":{"reactions":150,"comments":42,"followers":89,"posts":8}}
@app.get("/api/analytics/historical")
def analytics_historical(u=Depends(_auth)): return {"historical":[]}
@app.get("/api/analytics/past_day")
def analytics_past_day(u=Depends(_auth)): return {"past_day":[]}
@app.get("/api/analytics/referrers")
def analytics_referrers(u=Depends(_auth)): return {"referrers":[]}

# === Organizations (3) ===
@app.get("/api/organizations/{id_or_slug}")
def get_org(id_or_slug:str): return ORGS.get("org_1",{})

@app.get("/api/organizations/{id_or_slug}/users")
def org_users(id_or_slug:str): return list(USERS.values())[:2]

@app.get("/api/organizations/{id_or_slug}/articles")
def org_articles(id_or_slug:str): return list(ARTICLES.values())[:3]

# === Profile Images (1) ===
@app.get("/api/profile_images/{username}")
def profile_image(username:str): return {"image_of":"avatar","profile_image":"https://dev.to/avatar.jpg"}

# === Badges (5) ===
@app.get("/api/badges")
def list_badges(): return list(BADGES.values())
@app.get("/api/badges/{id}")
def get_badge(id:str): return BADGES.get(id,{})
@app.post("/api/badges")
def create_badge(u=Depends(_auth)): return {"id":"new","title":"New Badge"}
@app.put("/api/badges/{id}")
def update_badge(id:str,u=Depends(_auth)): return BADGES.get(id,{})
@app.delete("/api/badges/{id}")
def delete_badge(id:str,u=Depends(_auth)): return {}

# === Badge Achievements (4) ===
@app.get("/api/badge_achievements")
def list_badge_achievements(): return BADGE_ACHIEVEMENTS
@app.get("/api/badge_achievements/{id}")
def get_badge_achievement(id:str): return {}
@app.post("/api/badge_achievements")
def create_badge_achievement(u=Depends(_auth)): return {"id":"new"}
@app.delete("/api/badge_achievements/{id}")
def delete_badge_achievement(id:str,u=Depends(_auth)): return {}

# === Podcast Episodes & Videos (2) ===
@app.get("/api/podcast_episodes")
def list_podcasts(): return PODCASTS
@app.get("/api/videos")
def list_videos(): return VIDEOS

# === Health (3) ===
@app.get("/api/health_checks/app")
def hc_app(): return {"status":"ok"}
@app.get("/api/health_checks/database")
def hc_db(): return {"status":"ok"}
@app.get("/api/health_checks/cache")
def hc_cache(): return {"status":"ok"}

# === Instance & Subforems & Surveys (4) ===
@app.get("/api/instance")
def get_instance(): return {"name":"DEV Community","tagline":"Where programmers share ideas"}

@app.get("/api/subforems")
def list_subforems(): return []

@app.get("/api/surveys")
def list_surveys(): return []
@app.get("/api/surveys/{id}")
def get_survey(id:str): return {"id":id,"title":"Survey"}
