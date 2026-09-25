"""
Cal.com — Open Source Scheduling Platform — Route Replica
Source: https://github.com/calcom/cal.com
Stack: Next.js, file-based API routes (_get.ts, _post.ts, _patch.ts, _delete.ts)
Pattern: /api/v1/ prefix, API key auth, scheduling/calendaring
21 resource groups, 82 endpoints

Resources: api-keys, attendees, availabilities, availability, booking-references,
  bookings, connected-calendars, credential-sync, custom-inputs, destination-calendars,
  event-types, invites, me, memberships, payments, schedules, selected-calendars,
  slots, teams, users, webhooks
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Header, Query
from typing import Optional
import uuid, random, hashlib
from datetime import datetime, timedelta, date

USERS={}; BOOKINGS={}; EVENT_TYPES={}; SCHEDULES={}; TEAMS={}
AVAILABILITIES={}; ATTENDEES={}; WEBHOOKS={}; API_KEYS={}
MEMBERSHIPS={}; CUSTOM_INPUTS={}; BOOKING_REFS={}
DEST_CALENDARS={}; SEL_CALENDARS={}

def _auth(authorization:Optional[str]=Header(None)):
    if not authorization: raise HTTPException(401, "API key required")
    # Cal.com uses API key auth: ?apiKey=xxx or Authorization: Bearer xxx
    return {"id":"user_1","email":"user@cal.com","name":"Cal User","username":"caluser"}

def seed():
    for i in range(3):
        uid=f"user_{i+1}"
        USERS[uid]={"id":uid,"email":f"user{i+1}@cal.com","name":f"User {i+1}",
                    "username":f"user{i+1}","timeZone":"America/New_York","weekStart":"Monday",
                    "createdAt":datetime.utcnow().isoformat()}

    for i in range(5):
        eid=f"et_{i+1}"
        EVENT_TYPES[eid]={"id":eid,"title":["30min Meeting","1hr Consultation","Quick Chat","Workshop","Interview"][i],
                          "slug":["30min","1hr-consult","quick-chat","workshop","interview"][i],
                          "length":[30,60,15,120,45][i],"userId":"user_1",
                          "description":"Event type description","locations":[{"type":"integrations:google:meet"}],
                          "hidden":False,"requiresConfirmation":i>2}

    for i in range(8):
        bid=f"booking_{i+1}"
        BOOKINGS[bid]={"id":bid,"uid":str(uuid.uuid4()),"title":f"Meeting with Client {i+1}",
                       "description":"","startTime":(datetime.utcnow()+timedelta(days=i+1)).isoformat(),
                       "endTime":(datetime.utcnow()+timedelta(days=i+1,hours=1)).isoformat(),
                       "eventTypeId":f"et_{i%5+1}","userId":"user_1","status":["ACCEPTED","PENDING","CANCELLED"][i%3],
                       "attendees":[{"email":f"client{i+1}@example.com","name":f"Client {i+1}"}]}

    for i in range(3):
        sid=f"sched_{i+1}"
        SCHEDULES[sid]={"id":sid,"userId":"user_1","name":["Working Hours","Weekends Only","Extended"][i],
                        "timeZone":"America/New_York",
                        "availability":[{"days":[1,2,3,4,5],"startTime":"09:00","endTime":"17:00"}]}

    TEAMS["team_1"]={"id":"team_1","name":"Engineering","slug":"engineering","bio":"Dev team","members":["user_1","user_2"]}
    TEAMS["team_2"]={"id":"team_2","name":"Sales","slug":"sales","bio":"Sales team","members":["user_1","user_3"]}

    for i in range(3):
        AVAILABILITIES[f"avail_{i+1}"]={"id":f"avail_{i+1}","userId":"user_1","scheduleId":f"sched_{i%3+1}",
                                         "days":[1,2,3,4,5],"startTime":"09:00","endTime":"17:00"}

    for i in range(4):
        ATTENDEES[f"att_{i+1}"]={"id":f"att_{i+1}","bookingId":f"booking_{i+1}",
                                  "email":f"client{i+1}@example.com","name":f"Client {i+1}","timeZone":"America/New_York"}

    for i in range(2):
        WEBHOOKS[f"wh_{i+1}"]={"id":f"wh_{i+1}","url":f"https://example.com/webhook{i+1}",
                                "eventTriggers":["BOOKING_CREATED","BOOKING_CANCELLED"],"active":True}

    API_KEYS["key_1"]={"id":"key_1","userId":"user_1","note":"Default","hashedKey":"xxx","expiresAt":None}

    MEMBERSHIPS["mem_1"]={"id":"mem_1","teamId":"team_1","userId":"user_1","role":"ADMIN","accepted":True}
    MEMBERSHIPS["mem_2"]={"id":"mem_2","teamId":"team_1","userId":"user_2","role":"MEMBER","accepted":True}

    CUSTOM_INPUTS["ci_1"]={"id":"ci_1","eventTypeId":"et_1","label":"Company Name","type":"text","required":True}

    BOOKING_REFS["br_1"]={"id":"br_1","type":"google_calendar","uid":"gcal_123","bookingId":"booking_1"}

    DEST_CALENDARS["dc_1"]={"id":"dc_1","integration":"google_calendar","externalId":"primary","userId":"user_1"}
    SEL_CALENDARS["sc_1"]={"id":"sc_1","integration":"google_calendar","externalId":"primary","userId":"user_1"}

@asynccontextmanager
async def lifespan(app): seed(); yield
app = FastAPI(title="Cal.com", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

# Helper: standard CRUD for a resource
def _crud(resource_dict, prefix, name):
    """Generate standard CRUD routes. Returns (list, get, create, update, delete) fns."""

    @app.get(f"/api/v1/{prefix}")
    def list_items(u=Depends(_auth)): return {name: list(resource_dict.values())}

    @app.get(f"/api/v1/{prefix}/{{id}}")
    def get_item(id:str, u=Depends(_auth)):
        if id not in resource_dict: raise HTTPException(404)
        return {name[:-1] if name.endswith("s") else name: resource_dict[id]}

    @app.post(f"/api/v1/{prefix}")
    def create_item(u=Depends(_auth)):
        nid=f"{prefix}_{uuid.uuid4().hex[:6]}"
        return {name[:-1] if name.endswith("s") else name: {"id":nid}}

    @app.patch(f"/api/v1/{prefix}/{{id}}")
    def update_item(id:str, u=Depends(_auth)):
        if id not in resource_dict: raise HTTPException(404)
        return {name[:-1] if name.endswith("s") else name: resource_dict.get(id,{})}

    @app.delete(f"/api/v1/{prefix}/{{id}}")
    def delete_item(id:str, u=Depends(_auth)):
        return {"message":"Deleted"}

# === Standard CRUD resources (5 endpoints each × 12 = 60) ===
_crud(API_KEYS, "api-keys", "apiKeys")
_crud(ATTENDEES, "attendees", "attendees")
_crud(AVAILABILITIES, "availabilities", "availabilities")
_crud(BOOKING_REFS, "booking-references", "bookingReferences")
_crud(BOOKINGS, "bookings", "bookings")
_crud(CUSTOM_INPUTS, "custom-inputs", "customInputs")
_crud(DEST_CALENDARS, "destination-calendars", "destinationCalendars")
_crud(EVENT_TYPES, "event-types", "eventTypes")
_crud(MEMBERSHIPS, "memberships", "memberships")
_crud(SCHEDULES, "schedules", "schedules")
_crud(SEL_CALENDARS, "selected-calendars", "selectedCalendars")
_crud(WEBHOOKS, "webhooks", "webhooks")

# === Users (5) ===
@app.get("/api/v1/users")
def list_users(u=Depends(_auth)): return {"users":list(USERS.values())}
@app.get("/api/v1/users/{userId}")
def get_user(userId:str,u=Depends(_auth)):
    if userId not in USERS: raise HTTPException(404)
    return {"user":USERS[userId]}
@app.post("/api/v1/users")
def create_user(u=Depends(_auth)): return {"user":{"id":f"user_{uuid.uuid4().hex[:6]}"}}
@app.patch("/api/v1/users/{userId}")
def update_user(userId:str,u=Depends(_auth)): return {"user":USERS.get(userId,{})}
@app.delete("/api/v1/users/{userId}")
def delete_user(userId:str,u=Depends(_auth)): return {"message":"Deleted"}

# === Teams (5 + 2 nested) ===
@app.get("/api/v1/teams")
def list_teams(u=Depends(_auth)): return {"teams":list(TEAMS.values())}
@app.get("/api/v1/teams/{teamId}")
def get_team(teamId:str,u=Depends(_auth)): return {"team":TEAMS.get(teamId,{})}
@app.post("/api/v1/teams")
def create_team(u=Depends(_auth)): return {"team":{"id":f"team_{uuid.uuid4().hex[:6]}"}}
@app.patch("/api/v1/teams/{teamId}")
def update_team(teamId:str,u=Depends(_auth)): return {"team":TEAMS.get(teamId,{})}
@app.delete("/api/v1/teams/{teamId}")
def delete_team(teamId:str,u=Depends(_auth)): return {"message":"Deleted"}
@app.get("/api/v1/teams/{teamId}/event-types")
def team_event_types(teamId:str,u=Depends(_auth)): return {"eventTypes":[]}
@app.get("/api/v1/teams/{teamId}/availability")
def team_availability(teamId:str,u=Depends(_auth)): return {"availability":{}}

# === Me (1) ===
@app.get("/api/v1/me")
def get_me(u=Depends(_auth)): return {"user":u}

# === Availability (non-CRUD, just GET) ===
@app.get("/api/v1/availability")
def check_availability(dateFrom:Optional[str]=Query(None),dateTo:Optional[str]=Query(None),
                       u=Depends(_auth)):
    return {"busy":[],"timeZone":"America/New_York","dateRanges":[]}

# === Slots (1) ===
@app.get("/api/v1/slots")
def get_slots(eventTypeId:Optional[str]=Query(None),startTime:Optional[str]=Query(None),
              endTime:Optional[str]=Query(None)):
    return {"slots":{"2026-04-15":["09:00","09:30","10:00","10:30","11:00"]}}

# === Bookings nested (4) ===
@app.get("/api/v1/bookings/{id}/recordings")
def booking_recordings(id:str,u=Depends(_auth)): return {"recordings":[]}
@app.get("/api/v1/bookings/{id}/transcripts")
def booking_transcripts(id:str,u=Depends(_auth)): return {"transcripts":[]}
@app.get("/api/v1/bookings/{id}/transcripts/{recordingId}")
def booking_transcript_detail(id:str,recordingId:str,u=Depends(_auth)): return {"transcript":{}}

# === Connected Calendars (1) ===
@app.get("/api/v1/connected-calendars")
def connected_calendars(u=Depends(_auth)): return {"connectedCalendars":[]}

# === Credential Sync (4) ===
@app.get("/api/v1/credential-sync")
def get_cred_sync(u=Depends(_auth)): return {"credentials":[]}
@app.post("/api/v1/credential-sync")
def create_cred_sync(u=Depends(_auth)): return {"credential":{"id":"cred_1"}}
@app.patch("/api/v1/credential-sync")
def update_cred_sync(u=Depends(_auth)): return {"credential":{}}
@app.delete("/api/v1/credential-sync")
def delete_cred_sync(u=Depends(_auth)): return {"message":"Deleted"}

# === Invites (1) ===
@app.post("/api/v1/invites")
def create_invite(u=Depends(_auth)): return {"invite":{"id":"inv_1","token":"xxx"}}

# === Payments (placeholder) ===
@app.get("/api/v1/payments")
def list_payments(u=Depends(_auth)): return {"payments":[]}

# === Users availability (1) ===
@app.get("/api/v1/users/{userId}/availability")
def user_availability(userId:str,u=Depends(_auth)): return {"availability":{}}
