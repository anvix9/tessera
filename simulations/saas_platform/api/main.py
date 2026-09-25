"""
Subway Phase 4 — Complex API Simulation
A realistic SaaS project management platform (like Linear/Jira)

Patterns covered:
  1. PAGINATION — offset, cursor, page-based (3 styles on different endpoints)
  2. NESTED RESOURCES — projects/{id}/tasks/{id}/comments/{id} (3 levels)
  3. FILE UPLOADS — multipart, presigned URLs
  4. RATE LIMITING — per-endpoint, burst detection, 429 + Retry-After
  5. API VERSIONING — /v1/ and /v2/ with breaking changes
  6. RETRY LOGIC — 503 Service Unavailable with Retry-After
  7. COOKIES — session management, CSRF tokens
  8. BULK OPERATIONS — batch create/update/delete
  9. FILTERING & SORTING — complex query params
  10. ETAGS — conditional GET/PUT (If-None-Match, If-Match)
  11. WEBHOOKS — subscription, delivery, retry
  12. LONG-RUNNING OPERATIONS — async jobs with polling
  13. FIELD SELECTION — sparse fieldsets (?fields=id,name,status)
  14. EXPANSION — ?expand=assignee,project (inline related resources)

Total: ~45 endpoints demonstrating every complex pattern
"""
from contextlib import asynccontextmanager
from fastapi import (FastAPI, HTTPException, Depends, Header, Query, Request,
                     Response, UploadFile, File, Cookie)
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import uuid, random, hashlib, jwt, time, json, math
from datetime import datetime, timedelta
from collections import defaultdict

JWT_SECRET = "saas-platform-secret"
API_VERSION = "2"

# === Data stores ===
USERS = {}; EMAIL_IDX = {}
PROJECTS = {}; TASKS = {}; COMMENTS = {}
ATTACHMENTS = {}; WEBHOOKS = {}; JOBS = {}
SESSIONS = {}; CSRF_TOKENS = {}

# Rate limit tracking
RATE_LIMITS = defaultdict(list)  # user_id -> [timestamps]
RATE_CONFIG = {
    "default": {"requests": 100, "window": 60},
    "search": {"requests": 20, "window": 60},
    "upload": {"requests": 5, "window": 60},
    "bulk": {"requests": 3, "window": 60},
}

# ETag tracking
ETAGS = {}  # resource_key -> etag

def _hash(pw): return hashlib.sha256(f"saas-{pw}".encode()).hexdigest()
def _token(u): return jwt.encode({"sub": u["id"], "exp": datetime.utcnow() + timedelta(hours=24)}, JWT_SECRET)
def _etag(data): return hashlib.md5(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()

def _auth(authorization: Optional[str] = Header(None)):
    if not authorization: raise HTTPException(401, {"error": "unauthorized", "message": "Bearer token required"})
    try:
        t = authorization.replace("Bearer ", "")
        p = jwt.decode(t, JWT_SECRET, algorithms=["HS256"])
        u = USERS.get(p["sub"])
        if not u: raise HTTPException(401)
        return u
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, {"error": "token_expired", "message": "Token has expired. Please refresh."})
    except:
        raise HTTPException(401, {"error": "invalid_token"})


# === Rate Limiting Middleware ===
def _check_rate(user_id: str, endpoint_type: str = "default"):
    config = RATE_CONFIG.get(endpoint_type, RATE_CONFIG["default"])
    now = time.time()
    key = f"{user_id}:{endpoint_type}"

    # Clean old entries
    RATE_LIMITS[key] = [t for t in RATE_LIMITS[key] if now - t < config["window"]]

    if len(RATE_LIMITS[key]) >= config["requests"]:
        oldest = RATE_LIMITS[key][0]
        retry_after = int(config["window"] - (now - oldest)) + 1
        raise HTTPException(
            429,
            {
                "error": "rate_limit_exceeded",
                "message": f"Rate limit: {config['requests']} requests per {config['window']}s",
                "retry_after": retry_after,
                "limit": config["requests"],
                "remaining": 0,
                "reset": int(oldest + config["window"]),
            },
            headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(config["requests"]),
                     "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(oldest + config["window"]))}
        )

    RATE_LIMITS[key].append(now)
    remaining = config["requests"] - len(RATE_LIMITS[key])
    return remaining


def seed():
    # Users
    for uname, email, pw, role in [
        ("alice", "alice@saas.com", "pass123", "admin"),
        ("bob", "bob@saas.com", "pass456", "member"),
        ("charlie", "charlie@saas.com", "pass789", "viewer"),
    ]:
        uid = f"usr_{uuid.uuid4().hex[:8]}"
        USERS[uid] = {"id": uid, "username": uname, "email": email, "password_hash": _hash(pw),
                       "role": role, "full_name": uname.title(), "avatar_url": f"/avatars/{uname}.jpg",
                       "created_at": datetime.utcnow().isoformat(), "updated_at": datetime.utcnow().isoformat()}
        EMAIL_IDX[email] = uid

    admin_id = list(USERS.keys())[0]
    member_id = list(USERS.keys())[1]

    # Projects
    statuses = ["active", "archived", "planning"]
    for i in range(6):
        pid = f"proj_{i+1:03d}"
        PROJECTS[pid] = {
            "id": pid, "name": f"Project {'Alpha Beta Gamma Delta Epsilon Zeta'.split()[i]}",
            "slug": f"proj-{'alpha beta gamma delta epsilon zeta'.split()[i]}",
            "description": f"Description for project {i+1}",
            "status": statuses[i % 3], "owner_id": admin_id,
            "members": [admin_id, member_id],
            "settings": {"default_assignee": admin_id, "auto_close_days": 30},
            "created_at": (datetime.utcnow() - timedelta(days=90-i*10)).isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "task_count": 0,
        }

    # Tasks (nested under projects)
    priorities = ["critical", "high", "medium", "low"]
    task_statuses = ["backlog", "todo", "in_progress", "in_review", "done"]
    labels = ["bug", "feature", "improvement", "documentation", "security"]
    for i in range(50):
        tid = f"task_{i+1:04d}"
        pid = f"proj_{(i % 6) + 1:03d}"
        TASKS[tid] = {
            "id": tid, "project_id": pid,
            "title": f"Task #{i+1}: {'Fix bug in auth module,Implement search API,Add unit tests,Update documentation,Refactor database layer,Design new UI component,Optimize query performance,Add caching layer,Setup CI/CD pipeline,Review security audit'.split(',')[i % 10]}",
            "description": f"Detailed description for task {i+1}...",
            "status": task_statuses[i % 5],
            "priority": priorities[i % 4],
            "labels": [labels[i % 5], labels[(i+2) % 5]],
            "assignee_id": [admin_id, member_id][i % 2],
            "reporter_id": admin_id,
            "story_points": random.choice([1, 2, 3, 5, 8, 13]),
            "due_date": (datetime.utcnow() + timedelta(days=random.randint(1, 60))).date().isoformat(),
            "created_at": (datetime.utcnow() - timedelta(days=random.randint(1, 60))).isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        PROJECTS[pid]["task_count"] += 1

    # Comments (nested under tasks)
    for i in range(100):
        cid = f"cmt_{i+1:04d}"
        tid = f"task_{(i % 50) + 1:04d}"
        COMMENTS[cid] = {
            "id": cid, "task_id": tid,
            "author_id": [admin_id, member_id][i % 2],
            "body": f"Comment {i+1}: This is a detailed response about the task...",
            "created_at": (datetime.utcnow() - timedelta(hours=random.randint(1, 500))).isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "reactions": {"thumbs_up": random.randint(0, 5), "heart": random.randint(0, 3)},
        }

    # Attachments
    for i in range(10):
        aid = f"att_{i+1:03d}"
        tid = f"task_{(i % 20) + 1:04d}"
        ATTACHMENTS[aid] = {
            "id": aid, "task_id": tid,
            "filename": f"{'screenshot,report,design,spec,log'.split(',')[i%5]}_{i+1}.{'png,pdf,fig,md,txt'.split(',')[i%5]}",
            "content_type": f"{'image/png,application/pdf,application/octet-stream,text/markdown,text/plain'.split(',')[i%5]}",
            "size_bytes": random.randint(1024, 10485760),
            "url": f"/files/{aid}",
            "uploaded_by": admin_id,
            "created_at": datetime.utcnow().isoformat(),
        }


@asynccontextmanager
async def lifespan(app): seed(); yield
app = FastAPI(title="SaaS Platform", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


# ══════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    email: str = "alice@saas.com"
    password: str = "pass123"

@app.post("/v2/auth/login")
def login(body: LoginRequest, response: Response):
    """Login with email/password. Returns JWT + sets session cookie."""
    email = body.email
    uid = EMAIL_IDX.get(email)
    if not uid:
        raise HTTPException(401, {"error": "invalid_credentials"})

    user = USERS[uid]
    if user["password_hash"] != _hash(body.password):
        raise HTTPException(401, {"error": "invalid_credentials"})

    token = _token(user)

    # Set session cookie
    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = {"user_id": uid, "created_at": time.time(), "expires_at": time.time() + 86400}
    csrf = uuid.uuid4().hex
    CSRF_TOKENS[session_id] = csrf

    response.set_cookie("session_id", session_id, httponly=True, samesite="lax", max_age=86400)
    response.set_cookie("csrf_token", csrf, samesite="lax", max_age=86400)

    return {"access_token": token, "token_type": "bearer", "expires_in": 86400,
            "user": {"id": user["id"], "email": user["email"], "role": user["role"]}}

@app.post("/v2/auth/refresh")
def refresh_token(u=Depends(_auth)):
    """Refresh an expiring token."""
    return {"access_token": _token(u), "token_type": "bearer", "expires_in": 86400}

@app.get("/v2/auth/me")
def get_me(u=Depends(_auth)):
    return {"user": {k: v for k, v in u.items() if k != "password_hash"}}


# ══════════════════════════════════════════════════════════
# PROJECTS (basic CRUD + nested resources)
# ══════════════════════════════════════════════════════════

@app.get("/v2/projects")
def list_projects(
    status: Optional[str] = Query(None, description="Filter by status: active, archived, planning"),
    sort: Optional[str] = Query("created_at", description="Sort field"),
    order: Optional[str] = Query("desc", description="Sort order: asc, desc"),
    fields: Optional[str] = Query(None, description="Sparse fieldset: id,name,status"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page"),
    u=Depends(_auth),
):
    """List projects — PAGE-BASED pagination with filtering, sorting, field selection."""
    _check_rate(u["id"])
    items = list(PROJECTS.values())

    # Filter
    if status:
        items = [p for p in items if p["status"] == status]

    # Sort
    reverse = order == "desc"
    items.sort(key=lambda x: x.get(sort, ""), reverse=reverse)

    # Paginate (page-based)
    total = len(items)
    total_pages = math.ceil(total / per_page)
    start = (page - 1) * per_page
    items = items[start:start + per_page]

    # Sparse fieldset
    if fields:
        field_list = [f.strip() for f in fields.split(",")]
        items = [{k: v for k, v in p.items() if k in field_list} for p in items]

    return {
        "data": items,
        "pagination": {
            "page": page, "per_page": per_page,
            "total": total, "total_pages": total_pages,
            "has_next": page < total_pages, "has_prev": page > 1,
        }
    }


@app.get("/v2/projects/{project_id}")
def get_project(
    project_id: str,
    expand: Optional[str] = Query(None, description="Expand related: owner,members,tasks"),
    response: Response = None,
    if_none_match: Optional[str] = Header(None),
    u=Depends(_auth),
):
    """Get project detail — supports ETag + expansion."""
    if project_id not in PROJECTS:
        raise HTTPException(404, {"error": "not_found", "message": f"Project {project_id} not found"})

    project = PROJECTS[project_id]
    etag = _etag(project)

    # ETag: conditional GET
    if if_none_match and if_none_match.strip('"') == etag:
        return Response(status_code=304)

    result = {**project}

    # Expansion
    if expand:
        expansions = [e.strip() for e in expand.split(",")]
        if "owner" in expansions:
            owner = USERS.get(project["owner_id"])
            result["owner"] = {k: v for k, v in owner.items() if k != "password_hash"} if owner else None
        if "members" in expansions:
            result["members_detail"] = [
                {k: v for k, v in USERS[mid].items() if k != "password_hash"}
                for mid in project["members"] if mid in USERS
            ]
        if "tasks" in expansions:
            result["tasks"] = [t for t in TASKS.values() if t["project_id"] == project_id][:10]

    response.headers["ETag"] = f'"{etag}"'
    response.headers["Cache-Control"] = "private, max-age=60"
    return {"data": result}


@app.post("/v2/projects")
def create_project(u=Depends(_auth)):
    _check_rate(u["id"])
    pid = f"proj_{uuid.uuid4().hex[:6]}"
    PROJECTS[pid] = {"id": pid, "name": "New Project", "status": "planning",
                     "owner_id": u["id"], "members": [u["id"]],
                     "created_at": datetime.utcnow().isoformat(),
                     "updated_at": datetime.utcnow().isoformat(), "task_count": 0}
    return JSONResponse({"data": PROJECTS[pid]}, status_code=201,
                        headers={"Location": f"/v2/projects/{pid}"})

@app.patch("/v2/projects/{project_id}")
def update_project(
    project_id: str, response: Response,
    if_match: Optional[str] = Header(None),
    u=Depends(_auth),
):
    """Update project — supports ETag conditional update (If-Match)."""
    if project_id not in PROJECTS:
        raise HTTPException(404)

    project = PROJECTS[project_id]

    # ETag: conditional update — prevent concurrent modification
    if if_match:
        current_etag = _etag(project)
        if if_match.strip('"') != current_etag:
            raise HTTPException(412, {"error": "precondition_failed",
                                       "message": "Resource has been modified. Fetch the latest version and retry."})

    project["updated_at"] = datetime.utcnow().isoformat()
    new_etag = _etag(project)
    response.headers["ETag"] = f'"{new_etag}"'
    return {"data": project}

@app.delete("/v2/projects/{project_id}")
def delete_project(project_id: str, u=Depends(_auth)):
    if project_id not in PROJECTS: raise HTTPException(404)
    del PROJECTS[project_id]
    return Response(status_code=204)


# ══════════════════════════════════════════════════════════
# TASKS (nested under projects) — CURSOR-BASED pagination
# ══════════════════════════════════════════════════════════

@app.get("/v2/projects/{project_id}/tasks")
def list_tasks(
    project_id: str,
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    label: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Search in title/description"),
    sort: Optional[str] = Query("created_at"),
    order: Optional[str] = Query("desc"),
    cursor: Optional[str] = Query(None, description="Cursor for pagination (task ID)"),
    limit: int = Query(20, ge=1, le=100),
    expand: Optional[str] = Query(None, description="Expand: assignee,reporter,comments_count"),
    u=Depends(_auth),
):
    """List tasks — CURSOR-BASED pagination with rich filtering."""
    _check_rate(u["id"], "search" if q else "default")

    if project_id not in PROJECTS:
        raise HTTPException(404, {"error": "not_found"})

    items = [t for t in TASKS.values() if t["project_id"] == project_id]

    # Filters
    if status: items = [t for t in items if t["status"] == status]
    if priority: items = [t for t in items if t["priority"] == priority]
    if assignee_id: items = [t for t in items if t.get("assignee_id") == assignee_id]
    if label: items = [t for t in items if label in t.get("labels", [])]
    if q: items = [t for t in items if q.lower() in t["title"].lower() or q.lower() in t.get("description", "").lower()]

    # Sort
    items.sort(key=lambda x: x.get(sort, ""), reverse=(order == "desc"))

    # Cursor-based pagination
    if cursor:
        idx = next((i for i, t in enumerate(items) if t["id"] == cursor), -1)
        if idx >= 0:
            items = items[idx + 1:]

    has_more = len(items) > limit
    items = items[:limit]
    next_cursor = items[-1]["id"] if has_more and items else None

    # Expansion
    if expand:
        expansions = [e.strip() for e in expand.split(",")]
        for task in items:
            if "assignee" in expansions and task.get("assignee_id"):
                a = USERS.get(task["assignee_id"])
                task["assignee"] = {"id": a["id"], "username": a["username"]} if a else None
            if "reporter" in expansions and task.get("reporter_id"):
                r = USERS.get(task["reporter_id"])
                task["reporter"] = {"id": r["id"], "username": r["username"]} if r else None
            if "comments_count" in expansions:
                task["comments_count"] = sum(1 for c in COMMENTS.values() if c["task_id"] == task["id"])

    return {
        "data": items,
        "pagination": {
            "cursor": next_cursor,
            "has_more": has_more,
            "limit": limit,
            "total": sum(1 for t in TASKS.values() if t["project_id"] == project_id),
        }
    }


@app.post("/v2/projects/{project_id}/tasks")
def create_task(project_id: str, u=Depends(_auth)):
    _check_rate(u["id"])
    if project_id not in PROJECTS: raise HTTPException(404)
    tid = f"task_{uuid.uuid4().hex[:6]}"
    TASKS[tid] = {"id": tid, "project_id": project_id, "title": "New Task",
                  "status": "backlog", "priority": "medium", "assignee_id": u["id"],
                  "reporter_id": u["id"], "labels": [], "story_points": 0,
                  "created_at": datetime.utcnow().isoformat(), "updated_at": datetime.utcnow().isoformat()}
    PROJECTS[project_id]["task_count"] += 1
    return JSONResponse({"data": TASKS[tid]}, status_code=201)

@app.get("/v2/projects/{project_id}/tasks/{task_id}")
def get_task(project_id: str, task_id: str, expand: Optional[str] = Query(None),
             response: Response = None, u=Depends(_auth)):
    if task_id not in TASKS: raise HTTPException(404)
    task = TASKS[task_id]
    if task["project_id"] != project_id: raise HTTPException(404)
    etag = _etag(task)
    response.headers["ETag"] = f'"{etag}"'
    return {"data": task}

@app.patch("/v2/projects/{project_id}/tasks/{task_id}")
def update_task(project_id: str, task_id: str, u=Depends(_auth)):
    if task_id not in TASKS: raise HTTPException(404)
    TASKS[task_id]["updated_at"] = datetime.utcnow().isoformat()
    return {"data": TASKS[task_id]}

@app.delete("/v2/projects/{project_id}/tasks/{task_id}")
def delete_task(project_id: str, task_id: str, u=Depends(_auth)):
    if task_id not in TASKS: raise HTTPException(404)
    del TASKS[task_id]
    return Response(status_code=204)


# ══════════════════════════════════════════════════════════
# COMMENTS (3-level nesting) — OFFSET-BASED pagination
# ══════════════════════════════════════════════════════════

@app.get("/v2/projects/{project_id}/tasks/{task_id}/comments")
def list_comments(
    project_id: str, task_id: str,
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(20, ge=1, le=100),
    u=Depends(_auth),
):
    """List comments — OFFSET-BASED pagination (third style)."""
    items = sorted(
        [c for c in COMMENTS.values() if c["task_id"] == task_id],
        key=lambda x: x["created_at"],
    )
    total = len(items)
    items = items[offset:offset + limit]

    return {
        "data": items,
        "pagination": {"offset": offset, "limit": limit, "total": total,
                       "has_more": offset + limit < total}
    }

@app.post("/v2/projects/{project_id}/tasks/{task_id}/comments")
def create_comment(project_id: str, task_id: str, u=Depends(_auth)):
    cid = f"cmt_{uuid.uuid4().hex[:6]}"
    COMMENTS[cid] = {"id": cid, "task_id": task_id, "author_id": u["id"],
                     "body": "New comment", "created_at": datetime.utcnow().isoformat(),
                     "updated_at": datetime.utcnow().isoformat(), "reactions": {}}
    return JSONResponse({"data": COMMENTS[cid]}, status_code=201)

@app.get("/v2/projects/{project_id}/tasks/{task_id}/comments/{comment_id}")
def get_comment(project_id: str, task_id: str, comment_id: str, u=Depends(_auth)):
    if comment_id not in COMMENTS: raise HTTPException(404)
    return {"data": COMMENTS[comment_id]}

@app.patch("/v2/projects/{project_id}/tasks/{task_id}/comments/{comment_id}")
def update_comment(project_id: str, task_id: str, comment_id: str, u=Depends(_auth)):
    if comment_id not in COMMENTS: raise HTTPException(404)
    COMMENTS[comment_id]["updated_at"] = datetime.utcnow().isoformat()
    return {"data": COMMENTS[comment_id]}

@app.delete("/v2/projects/{project_id}/tasks/{task_id}/comments/{comment_id}")
def delete_comment(project_id: str, task_id: str, comment_id: str, u=Depends(_auth)):
    if comment_id not in COMMENTS: raise HTTPException(404)
    del COMMENTS[comment_id]
    return Response(status_code=204)


# ══════════════════════════════════════════════════════════
# FILE UPLOADS — multipart + presigned URL pattern
# ══════════════════════════════════════════════════════════

@app.post("/v2/projects/{project_id}/tasks/{task_id}/attachments")
def upload_attachment(project_id: str, task_id: str,
                      file: UploadFile = File(None),
                      u=Depends(_auth)):
    """Upload file as multipart form data."""
    _check_rate(u["id"], "upload")
    aid = f"att_{uuid.uuid4().hex[:6]}"
    filename = file.filename if file else "unnamed.bin"
    ATTACHMENTS[aid] = {
        "id": aid, "task_id": task_id, "filename": filename,
        "content_type": file.content_type if file else "application/octet-stream",
        "size_bytes": 0, "url": f"/files/{aid}",
        "uploaded_by": u["id"], "created_at": datetime.utcnow().isoformat(),
    }
    return JSONResponse({"data": ATTACHMENTS[aid]}, status_code=201)

@app.post("/v2/uploads/presign")
def get_presigned_url(u=Depends(_auth)):
    """Get a presigned URL for direct upload to object storage."""
    _check_rate(u["id"], "upload")
    upload_id = uuid.uuid4().hex
    return {
        "upload_id": upload_id,
        "presigned_url": f"https://storage.example.com/uploads/{upload_id}",
        "expires_in": 3600,
        "method": "PUT",
        "headers": {"Content-Type": "application/octet-stream", "x-upload-id": upload_id},
    }

@app.get("/v2/projects/{project_id}/tasks/{task_id}/attachments")
def list_attachments(project_id: str, task_id: str, u=Depends(_auth)):
    items = [a for a in ATTACHMENTS.values() if a["task_id"] == task_id]
    return {"data": items, "count": len(items)}

@app.delete("/v2/projects/{project_id}/tasks/{task_id}/attachments/{attachment_id}")
def delete_attachment(project_id: str, task_id: str, attachment_id: str, u=Depends(_auth)):
    if attachment_id not in ATTACHMENTS: raise HTTPException(404)
    del ATTACHMENTS[attachment_id]
    return Response(status_code=204)


# ══════════════════════════════════════════════════════════
# BULK OPERATIONS
# ══════════════════════════════════════════════════════════

@app.post("/v2/projects/{project_id}/tasks/bulk")
def bulk_task_operations(project_id: str, u=Depends(_auth)):
    """Batch create/update/delete tasks. Body: {operations: [{op, data}, ...]}"""
    _check_rate(u["id"], "bulk")
    # Simulate processing
    return {
        "data": {
            "processed": 5, "succeeded": 4, "failed": 1,
            "results": [
                {"op": "create", "status": "success", "id": f"task_{uuid.uuid4().hex[:6]}"},
                {"op": "update", "status": "success", "id": "task_0001"},
                {"op": "update", "status": "success", "id": "task_0002"},
                {"op": "delete", "status": "success", "id": "task_0003"},
                {"op": "update", "status": "error", "id": "task_9999", "error": "not_found"},
            ],
            "errors": [{"op": "update", "id": "task_9999", "error": "Task not found"}]
        }
    }

@app.post("/v2/tasks/bulk-update")
def bulk_update_tasks(u=Depends(_auth)):
    """Update multiple tasks across projects. Body: {task_ids: [...], changes: {...}}"""
    _check_rate(u["id"], "bulk")
    return {"data": {"updated": 10, "failed": 0}}


# ══════════════════════════════════════════════════════════
# WEBHOOKS — subscription management
# ══════════════════════════════════════════════════════════

@app.get("/v2/webhooks")
def list_webhooks(u=Depends(_auth)):
    items = [w for w in WEBHOOKS.values() if w.get("created_by") == u["id"]]
    return {"data": items}

@app.post("/v2/webhooks")
def create_webhook(u=Depends(_auth)):
    wid = f"wh_{uuid.uuid4().hex[:6]}"
    WEBHOOKS[wid] = {
        "id": wid, "url": "https://example.com/webhook",
        "events": ["task.created", "task.updated", "task.deleted"],
        "secret": uuid.uuid4().hex, "active": True,
        "created_by": u["id"], "created_at": datetime.utcnow().isoformat(),
        "delivery_stats": {"total": 0, "succeeded": 0, "failed": 0},
    }
    return JSONResponse({"data": WEBHOOKS[wid]}, status_code=201)

@app.get("/v2/webhooks/{webhook_id}")
def get_webhook(webhook_id: str, u=Depends(_auth)):
    if webhook_id not in WEBHOOKS: raise HTTPException(404)
    return {"data": WEBHOOKS[webhook_id]}

@app.patch("/v2/webhooks/{webhook_id}")
def update_webhook(webhook_id: str, u=Depends(_auth)):
    if webhook_id not in WEBHOOKS: raise HTTPException(404)
    return {"data": WEBHOOKS[webhook_id]}

@app.delete("/v2/webhooks/{webhook_id}")
def delete_webhook(webhook_id: str, u=Depends(_auth)):
    if webhook_id not in WEBHOOKS: raise HTTPException(404)
    del WEBHOOKS[webhook_id]
    return Response(status_code=204)

@app.get("/v2/webhooks/{webhook_id}/deliveries")
def list_deliveries(webhook_id: str, u=Depends(_auth)):
    """List recent webhook delivery attempts with status."""
    return {"data": [
        {"id": f"del_{i}", "event": "task.updated", "status": ["success", "success", "failed"][i % 3],
         "response_code": [200, 200, 500][i % 3], "delivered_at": datetime.utcnow().isoformat(),
         "retry_count": 0 if i % 3 != 2 else 3}
        for i in range(5)
    ]}

@app.post("/v2/webhooks/{webhook_id}/test")
def test_webhook(webhook_id: str, u=Depends(_auth)):
    """Send a test webhook delivery."""
    return {"data": {"status": "delivered", "response_code": 200, "latency_ms": 142}}


# ══════════════════════════════════════════════════════════
# LONG-RUNNING OPERATIONS — async jobs with polling
# ══════════════════════════════════════════════════════════

@app.post("/v2/projects/{project_id}/export")
def export_project(project_id: str, u=Depends(_auth)):
    """Start async export. Returns job ID for polling."""
    if project_id not in PROJECTS: raise HTTPException(404)
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    JOBS[job_id] = {
        "id": job_id, "type": "project_export", "status": "processing",
        "project_id": project_id, "progress": 0,
        "created_at": datetime.utcnow().isoformat(),
        "result_url": None,
    }
    return JSONResponse(
        {"data": {"job_id": job_id, "status": "processing", "poll_url": f"/v2/jobs/{job_id}"}},
        status_code=202,
        headers={"Location": f"/v2/jobs/{job_id}"}
    )

@app.get("/v2/jobs/{job_id}")
def get_job_status(job_id: str, u=Depends(_auth)):
    """Poll job status. When complete, includes result_url."""
    if job_id not in JOBS: raise HTTPException(404)
    job = JOBS[job_id]

    # Simulate progress
    if job["status"] == "processing":
        job["progress"] = min(100, job["progress"] + random.randint(20, 40))
        if job["progress"] >= 100:
            job["status"] = "completed"
            job["result_url"] = f"/v2/jobs/{job_id}/download"
            job["completed_at"] = datetime.utcnow().isoformat()

    response_headers = {}
    if job["status"] == "processing":
        response_headers["Retry-After"] = "5"

    return JSONResponse({"data": job}, headers=response_headers)

@app.get("/v2/jobs/{job_id}/download")
def download_job_result(job_id: str, u=Depends(_auth)):
    if job_id not in JOBS: raise HTTPException(404)
    if JOBS[job_id]["status"] != "completed":
        raise HTTPException(409, {"error": "not_ready", "message": "Job still processing"})
    return {"data": {"download_url": f"https://storage.example.com/exports/{job_id}.zip",
                     "expires_in": 3600}}


# ══════════════════════════════════════════════════════════
# SEARCH (global, rate-limited)
# ══════════════════════════════════════════════════════════

@app.get("/v2/search")
def global_search(
    q: str = Query(..., min_length=2, description="Search query"),
    type: Optional[str] = Query(None, description="Filter: project, task, comment"),
    limit: int = Query(20, ge=1, le=50),
    u=Depends(_auth),
):
    """Global search with tighter rate limits."""
    _check_rate(u["id"], "search")
    results = []

    if not type or type == "project":
        results.extend([{"type": "project", **p} for p in PROJECTS.values()
                        if q.lower() in p["name"].lower()][:5])
    if not type or type == "task":
        results.extend([{"type": "task", **t} for t in TASKS.values()
                        if q.lower() in t["title"].lower()][:10])
    if not type or type == "comment":
        results.extend([{"type": "comment", **c} for c in COMMENTS.values()
                        if q.lower() in c["body"].lower()][:5])

    return {"data": results[:limit], "total": len(results), "query": q}


# ══════════════════════════════════════════════════════════
# V1 COMPATIBILITY (API versioning — deprecated endpoints)
# ══════════════════════════════════════════════════════════

@app.get("/v1/projects")
def list_projects_v1(u=Depends(_auth)):
    """Deprecated v1 endpoint — different response format."""
    return JSONResponse(
        {"projects": list(PROJECTS.values()), "total": len(PROJECTS)},
        headers={"Deprecation": "true", "Sunset": "2026-12-01",
                 "Link": '</v2/projects>; rel="successor-version"'}
    )

@app.get("/v1/projects/{project_id}/tasks")
def list_tasks_v1(project_id: str, page: int = Query(1), u=Depends(_auth)):
    """Deprecated v1 — uses page-based pagination (v2 uses cursor)."""
    items = [t for t in TASKS.values() if t["project_id"] == project_id]
    return JSONResponse(
        {"tasks": items[(page-1)*20:page*20], "page": page, "total": len(items)},
        headers={"Deprecation": "true", "Sunset": "2026-12-01"}
    )


# ══════════════════════════════════════════════════════════
# HEALTH & SERVICE STATUS
# ══════════════════════════════════════════════════════════

@app.get("/v2/health")
def health():
    return {"status": "healthy", "version": "2.0.0", "uptime_seconds": int(time.time())}

@app.get("/v2/health/detailed")
def health_detailed(u=Depends(_auth)):
    return {
        "status": "healthy", "version": "2.0.0",
        "services": {"database": "ok", "cache": "ok", "storage": "ok", "queue": "ok"},
        "stats": {"projects": len(PROJECTS), "tasks": len(TASKS), "users": len(USERS)},
    }
