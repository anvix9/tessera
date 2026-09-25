"""
FastAPI Full-Stack Template — Route Replica
Source: https://github.com/fastapi/full-stack-fastapi-template
Stack: Python/FastAPI + React frontend
Pattern: /api/v1/ prefix, JWT auth, CRUD items, user management
Endpoints: 23
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional
import uuid, hashlib, jwt
from datetime import datetime, timedelta

JWT_SECRET = "fastapi-fullstack-secret"

USERS = {}; EMAIL_INDEX = {}; ITEMS = {}

def _hash(pw): return hashlib.sha256(f"fs-{pw}".encode()).hexdigest()
def _token(u): return jwt.encode({"sub": u["id"], "exp": datetime.utcnow()+timedelta(hours=24)}, JWT_SECRET)
def _auth(authorization: Optional[str] = Header(None)):
    if not authorization: raise HTTPException(401, "Not authenticated")
    try:
        t = authorization.replace("Bearer ", "")
        p = jwt.decode(t, JWT_SECRET, algorithms=["HS256"])
        u = USERS.get(p["sub"])
        if not u: raise HTTPException(401)
        return u
    except: raise HTTPException(401)

def seed():
    for email, pw, name, su in [("admin@example.com","changethis","Admin",True),("user@example.com","password","User",False)]:
        uid = str(uuid.uuid4())
        USERS[uid] = {"id":uid,"email":email,"password_hash":_hash(pw),"full_name":name,"is_superuser":su,"is_active":True}
        EMAIL_INDEX[email] = uid
    for i in range(5):
        iid = str(uuid.uuid4())
        ITEMS[iid] = {"id":iid,"title":f"Item {i+1}","description":f"Description {i+1}","owner_id":list(USERS.keys())[0]}

@asynccontextmanager
async def lifespan(app): seed(); yield

app = FastAPI(title="FastAPI Full-Stack", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

# === Login (5) ===
class LoginReq(BaseModel): username: str; password: str
@app.post("/api/v1/login/access-token")
def login(req: LoginReq):
    uid = EMAIL_INDEX.get(req.username)
    if not uid or USERS[uid]["password_hash"] != _hash(req.password): raise HTTPException(400,"Incorrect")
    return {"access_token": _token(USERS[uid]), "token_type":"bearer"}

@app.post("/api/v1/login/test-token")
def test_token(u=Depends(_auth)): return {"email":u["email"],"full_name":u["full_name"]}

@app.post("/api/v1/password-recovery/{email}")
def recover(email:str): return {"message":"Recovery email sent"}

@app.post("/api/v1/reset-password")
def reset_pw(): return {"message":"Password reset"}

@app.post("/api/v1/password-recovery-html-content/{email}")
def recover_html(email:str): return {"message":"HTML recovery"}

# === Users (8) ===
@app.get("/api/v1/users")
def list_users(u=Depends(_auth)): return {"data":list(USERS.values()),"count":len(USERS)}

@app.post("/api/v1/users")
def create_user(u=Depends(_auth)): return {"id":str(uuid.uuid4()),"email":"new@test.com"}

@app.get("/api/v1/users/me")
def get_me(u=Depends(_auth)): return u

@app.patch("/api/v1/users/me")
def update_me(u=Depends(_auth)): return u

@app.patch("/api/v1/users/me/password")
def change_pw(u=Depends(_auth)): return {"message":"Password updated"}

@app.delete("/api/v1/users/me")
def delete_me(u=Depends(_auth)): return {"message":"User deleted"}

@app.post("/api/v1/users/signup")
def signup(): uid=str(uuid.uuid4()); USERS[uid]={"id":uid,"email":"new@test.com","full_name":"New","is_superuser":False,"is_active":True}; return USERS[uid]

@app.get("/api/v1/users/{user_id}")
def get_user(user_id:str,u=Depends(_auth)):
    if user_id not in USERS: raise HTTPException(404)
    return USERS[user_id]

@app.patch("/api/v1/users/{user_id}")
def update_user(user_id:str,u=Depends(_auth)): return USERS.get(user_id,{})

@app.delete("/api/v1/users/{user_id}")
def delete_user(user_id:str,u=Depends(_auth)): return {"message":"Deleted"}

# === Items (5) ===
@app.get("/api/v1/items")
def list_items(u=Depends(_auth)): return {"data":list(ITEMS.values()),"count":len(ITEMS)}

@app.get("/api/v1/items/{id}")
def get_item(id:str,u=Depends(_auth)):
    if id not in ITEMS: raise HTTPException(404)
    return ITEMS[id]

@app.post("/api/v1/items")
def create_item(u=Depends(_auth)): iid=str(uuid.uuid4()); ITEMS[iid]={"id":iid,"title":"New","owner_id":u["id"]}; return ITEMS[iid]

@app.put("/api/v1/items/{id}")
def update_item(id:str,u=Depends(_auth)): return ITEMS.get(id,{})

@app.delete("/api/v1/items/{id}")
def delete_item(id:str,u=Depends(_auth)): return {"message":"Deleted"}

# === Utils (1) ===
@app.get("/api/v1/utils/health-check")
def health(): return True
