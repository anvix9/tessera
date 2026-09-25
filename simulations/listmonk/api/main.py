"""
Listmonk — Newsletter & Mailing List Manager — Route Replica
Source: https://github.com/knadh/listmonk
Stack: Go/Echo, Vue.js frontend
Pattern: /api/ prefix, session auth, newsletter/email management
Key resources: subscribers, lists, campaigns, templates, bounces, media
Endpoints: 60 (core subset from 102 total)
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Header, Query
from typing import Optional
import uuid, random, hashlib, jwt
from datetime import datetime, timedelta

JWT_SECRET = "listmonk-secret"

SUBSCRIBERS={}; LISTS={}; CAMPAIGNS={}; TEMPLATES={}; BOUNCES={}; MEDIA={}; USERS_ADMIN={}
EMAIL_INDEX={}; ROLES={}

def _hash(pw): return hashlib.sha256(f"lm-{pw}".encode()).hexdigest()
def _token(u): return jwt.encode({"sub":u["id"],"exp":datetime.utcnow()+timedelta(hours=24)},JWT_SECRET)
def _auth(authorization:Optional[str]=Header(None)):
    if not authorization: raise HTTPException(401)
    try:
        p=jwt.decode(authorization.replace("Bearer ",""),JWT_SECRET,algorithms=["HS256"])
        return USERS_ADMIN.get(p["sub"])
    except: raise HTTPException(401)

def seed():
    # Admin users
    uid="admin_1"
    USERS_ADMIN[uid]={"id":uid,"username":"admin","email":"admin@listmonk.app","password_hash":_hash("admin123"),
                       "name":"Admin","type":"admin","status":"enabled"}
    EMAIL_INDEX["admin@listmonk.app"]=uid

    # Lists
    for i,(name,ltype,optin) in enumerate([("Newsletter","public","single"),("Product Updates","private","double"),
                                            ("Marketing","public","single"),("Internal","private","single")]):
        lid=f"list_{i+1}"
        LISTS[lid]={"id":lid,"uuid":str(uuid.uuid4()),"name":name,"type":ltype,"optin":optin,
                    "tags":["default"],"subscriber_count":random.randint(100,5000)}

    # Subscribers
    for i in range(15):
        sid=f"sub_{i+1}"
        SUBSCRIBERS[sid]={"id":sid,"uuid":str(uuid.uuid4()),"email":f"user{i+1}@example.com",
                          "name":f"User {i+1}","status":["enabled","blocklisted","unconfirmed"][i%3],
                          "lists":[random.choice(list(LISTS.keys()))],
                          "attribs":{"city":["NYC","London","Berlin","Tokyo"][i%4]},
                          "created_at":datetime.utcnow().isoformat()}

    # Campaigns
    for i,(name,status) in enumerate([("Welcome Series","running"),("Black Friday","finished"),
                                       ("Monthly Digest","draft"),("Product Launch","scheduled")]):
        cid=f"camp_{i+1}"
        CAMPAIGNS[cid]={"id":cid,"uuid":str(uuid.uuid4()),"name":name,"subject":f"{name} - Email",
                        "status":status,"type":"regular","body":"<h1>Hello!</h1>",
                        "content_type":"richtext","from_email":"noreply@app.com",
                        "lists":[list(LISTS.keys())[i%len(LISTS)]],
                        "tags":["campaign"],"send_at":datetime.utcnow().isoformat(),
                        "stats":{"sent":random.randint(0,5000),"views":random.randint(0,3000),
                                 "clicks":random.randint(0,500),"bounces":random.randint(0,50)}}

    # Templates
    for i,name in enumerate(["Default","Minimal","Marketing","Transactional"]):
        tid=f"tpl_{i+1}"
        TEMPLATES[tid]={"id":tid,"name":name,"body":"<html>{{template \"content\" .}}</html>",
                        "type":["campaign","tx"][i%2],"is_default":i==0}

    # Bounces
    for i in range(5):
        bid=f"bounce_{i+1}"
        BOUNCES[bid]={"id":bid,"subscriber_id":f"sub_{i+1}","email":f"user{i+1}@example.com",
                      "campaign_id":f"camp_{i%4+1}","type":["hard","soft"][i%2],
                      "source":"smtp","created_at":datetime.utcnow().isoformat()}

    # Media
    MEDIA["media_1"]={"id":"media_1","uuid":str(uuid.uuid4()),"filename":"logo.png",
                       "content_type":"image/png","thumb_url":"/media/thumb/logo.png"}

    # Roles
    ROLES["role_1"]={"id":"role_1","name":"admin","permissions":["all"]}
    ROLES["role_2"]={"id":"role_2","name":"editor","permissions":["campaigns:manage","lists:get"]}

@asynccontextmanager
async def lifespan(app): seed(); yield
app = FastAPI(title="Listmonk", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

# === System/Config (8) ===
@app.get("/api/health")
def health(): return {"status":"ok"}
@app.get("/api/config")
def config(u=Depends(_auth)): return {"config":{"version":"4.0.0"}}
@app.get("/api/about")
def about(): return {"version":"4.0.0","name":"listmonk"}
@app.get("/api/dashboard/charts")
def dash_charts(u=Depends(_auth)): return {"charts":[]}
@app.get("/api/dashboard/counts")
def dash_counts(u=Depends(_auth)): return {"subscribers":len(SUBSCRIBERS),"lists":len(LISTS),"campaigns":len(CAMPAIGNS)}
@app.get("/api/settings")
def get_settings(u=Depends(_auth)): return {"settings":{}}
@app.put("/api/settings")
def update_settings(u=Depends(_auth)): return {"settings":{}}
@app.get("/api/logs")
def get_logs(u=Depends(_auth)): return {"logs":[]}

# === Subscribers (14) ===
@app.get("/api/subscribers")
def list_subscribers(u=Depends(_auth)): return {"data":list(SUBSCRIBERS.values()),"total":len(SUBSCRIBERS)}
@app.get("/api/subscribers/{id}")
def get_subscriber(id:str,u=Depends(_auth)):
    if id not in SUBSCRIBERS: raise HTTPException(404)
    return {"data":SUBSCRIBERS[id]}
@app.get("/api/subscribers/{id}/activity")
def subscriber_activity(id:str,u=Depends(_auth)): return {"data":[]}
@app.get("/api/subscribers/{id}/export")
def export_subscriber(id:str,u=Depends(_auth)): return {"data":{}}
@app.get("/api/subscribers/{id}/bounces")
def subscriber_bounces(id:str,u=Depends(_auth)): return {"data":[]}
@app.delete("/api/subscribers/{id}/bounces")
def delete_sub_bounces(id:str,u=Depends(_auth)): return {}
@app.post("/api/subscribers")
def create_subscriber(u=Depends(_auth)): return {"data":{"id":f"sub_{uuid.uuid4().hex[:6]}"}}
@app.put("/api/subscribers/{id}")
def update_subscriber(id:str,u=Depends(_auth)): return {"data":SUBSCRIBERS.get(id,{})}
@app.delete("/api/subscribers/{id}")
def delete_subscriber(id:str,u=Depends(_auth)): return {}
@app.delete("/api/subscribers")
def delete_subscribers(u=Depends(_auth)): return {}
@app.post("/api/subscribers/{id}/optin")
def send_optin(id:str,u=Depends(_auth)): return {"data":True}
@app.put("/api/subscribers/{id}/blocklist")
def blocklist_subscriber(id:str,u=Depends(_auth)): return {"data":True}
@app.put("/api/subscribers/blocklist")
def blocklist_subscribers(u=Depends(_auth)): return {"data":True}
@app.get("/api/subscribers/export")
def export_subscribers(u=Depends(_auth)): return {"data":"csv_data"}

# === Lists (5) ===
@app.get("/api/lists")
def list_lists(u=Depends(_auth)): return {"data":list(LISTS.values()),"total":len(LISTS)}
@app.get("/api/lists/{id}")
def get_list(id:str,u=Depends(_auth)):
    if id not in LISTS: raise HTTPException(404)
    return {"data":LISTS[id]}
@app.post("/api/lists")
def create_list(u=Depends(_auth)): return {"data":{"id":f"list_{uuid.uuid4().hex[:6]}"}}
@app.put("/api/lists/{id}")
def update_list(id:str,u=Depends(_auth)): return {"data":LISTS.get(id,{})}
@app.delete("/api/lists/{id}")
def delete_list(id:str,u=Depends(_auth)): return {}

# === Campaigns (12) ===
@app.get("/api/campaigns")
def list_campaigns(u=Depends(_auth)): return {"data":list(CAMPAIGNS.values()),"total":len(CAMPAIGNS)}
@app.get("/api/campaigns/{id}")
def get_campaign(id:str,u=Depends(_auth)):
    if id not in CAMPAIGNS: raise HTTPException(404)
    return {"data":CAMPAIGNS[id]}
@app.get("/api/campaigns/{id}/preview")
def preview_campaign(id:str,u=Depends(_auth)): return {"data":"<html>Preview</html>"}
@app.get("/api/campaigns/running/stats")
def running_stats(u=Depends(_auth)): return {"data":[]}
@app.get("/api/campaigns/analytics/{type}")
def campaign_analytics(type:str,u=Depends(_auth)): return {"data":[]}
@app.post("/api/campaigns")
def create_campaign(u=Depends(_auth)): return {"data":{"id":f"camp_{uuid.uuid4().hex[:6]}"}}
@app.put("/api/campaigns/{id}")
def update_campaign(id:str,u=Depends(_auth)): return {"data":CAMPAIGNS.get(id,{})}
@app.put("/api/campaigns/{id}/status")
def update_campaign_status(id:str,u=Depends(_auth)): return {"data":CAMPAIGNS.get(id,{})}
@app.put("/api/campaigns/{id}/archive")
def archive_campaign(id:str,u=Depends(_auth)): return {"data":CAMPAIGNS.get(id,{})}
@app.post("/api/campaigns/{id}/test")
def test_campaign(id:str,u=Depends(_auth)): return {"data":True}
@app.post("/api/campaigns/{id}/content")
def campaign_content(id:str,u=Depends(_auth)): return {"data":"OK"}
@app.delete("/api/campaigns/{id}")
def delete_campaign(id:str,u=Depends(_auth)): return {}

# === Templates (6) ===
@app.get("/api/templates")
def list_templates(u=Depends(_auth)): return {"data":list(TEMPLATES.values())}
@app.get("/api/templates/{id}")
def get_template(id:str,u=Depends(_auth)): return {"data":TEMPLATES.get(id,{})}
@app.get("/api/templates/{id}/preview")
def preview_template(id:str,u=Depends(_auth)): return {"data":"<html>Preview</html>"}
@app.post("/api/templates")
def create_template(u=Depends(_auth)): return {"data":{"id":f"tpl_{uuid.uuid4().hex[:6]}"}}
@app.put("/api/templates/{id}")
def update_template(id:str,u=Depends(_auth)): return {"data":TEMPLATES.get(id,{})}
@app.put("/api/templates/{id}/default")
def set_default_template(id:str,u=Depends(_auth)): return {"data":True}
@app.delete("/api/templates/{id}")
def delete_template(id:str,u=Depends(_auth)): return {}

# === Bounces (4) ===
@app.get("/api/bounces")
def list_bounces(u=Depends(_auth)): return {"data":list(BOUNCES.values()),"total":len(BOUNCES)}
@app.get("/api/bounces/{id}")
def get_bounce(id:str,u=Depends(_auth)): return {"data":BOUNCES.get(id,{})}
@app.delete("/api/bounces/{id}")
def delete_bounce(id:str,u=Depends(_auth)): return {}
@app.delete("/api/bounces")
def delete_bounces(u=Depends(_auth)): return {}

# === Media (3) ===
@app.get("/api/media")
def list_media(u=Depends(_auth)): return {"data":list(MEDIA.values())}
@app.get("/api/media/{id}")
def get_media(id:str,u=Depends(_auth)): return {"data":MEDIA.get(id,{})}
@app.delete("/api/media/{id}")
def delete_media(id:str,u=Depends(_auth)): return {}

# === Users/Roles (6) ===
@app.get("/api/users")
def list_users(u=Depends(_auth)): return {"data":list(USERS_ADMIN.values())}
@app.get("/api/users/{id}")
def get_user(id:str,u=Depends(_auth)): return {"data":USERS_ADMIN.get(id,{})}
@app.post("/api/users")
def create_user(u=Depends(_auth)): return {"data":{"id":f"u_{uuid.uuid4().hex[:6]}"}}
@app.put("/api/users/{id}")
def update_user(id:str,u=Depends(_auth)): return {"data":USERS_ADMIN.get(id,{})}
@app.delete("/api/users/{id}")
def delete_user(id:str,u=Depends(_auth)): return {}
@app.get("/api/profile")
def get_profile(u=Depends(_auth)): return {"data":u}
@app.put("/api/profile")
def update_profile(u=Depends(_auth)): return {"data":u}

# === Import (3) ===
@app.get("/api/import/subscribers")
def get_import(u=Depends(_auth)): return {"data":{"status":"idle"}}
@app.get("/api/import/subscribers/logs")
def get_import_logs(u=Depends(_auth)): return {"data":""}
@app.post("/api/import/subscribers")
def start_import(u=Depends(_auth)): return {"data":{"status":"importing"}}
