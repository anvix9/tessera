"""
CampusCrib — Student Housing Board

A social platform where students:
- Post available rooms/apartments
- Browse listings by university, price, type, amenities
- Like, comment, share listings
- Message other students (landlords/roommates)
- Save favorites
- Post roommate-wanted ads
- Rate previous landlords/roommates
- View activity feed
- Paginated results

Endpoints (35 total):
  PUBLIC (10):
    GET  /api/listings                    - Browse room listings (paginated)
    GET  /api/listings/{id}               - Listing detail
    GET  /api/listings/featured           - Featured/promoted listings
    GET  /api/listings/nearby             - Listings near a university
    GET  /api/universities                - List universities
    GET  /api/universities/{id}           - University + nearby listings
    GET  /api/roommates                   - Roommate-wanted ads (paginated)
    GET  /api/roommates/{id}              - Roommate ad detail
    GET  /api/search                      - Global search
    GET  /api/site/info                   - Platform info

  AUTH (2):
    POST /api/auth/register               - Create student account
    POST /api/auth/login                  - Login

  PROTECTED (23):
    GET  /api/auth/profile                - User profile
    PUT  /api/auth/profile                - Update profile
    POST /api/listings                    - Create a room listing
    PUT  /api/listings/{id}               - Update own listing
    DELETE /api/listings/{id}             - Delete own listing
    POST /api/listings/{id}/like          - Like a listing
    POST /api/listings/{id}/unlike        - Unlike
    GET  /api/listings/{id}/comments      - Get comments
    POST /api/listings/{id}/comments      - Post comment
    POST /api/listings/{id}/share         - Share (track count)
    POST /api/listings/{id}/report        - Report listing
    POST /api/roommates                   - Post roommate-wanted ad
    POST /api/roommates/{id}/like         - Like an ad
    POST /api/roommates/{id}/comments     - Comment on ad
    GET  /api/messages                    - Inbox
    POST /api/messages                    - Send message
    GET  /api/messages/{id}               - Conversation thread
    GET  /api/favorites                   - Saved listings
    POST /api/favorites/add               - Save a listing
    POST /api/favorites/remove            - Remove from favorites
    GET  /api/feed                        - Activity feed
    GET  /api/me/listings                 - User's own listings
    GET  /api/notifications               - Notifications
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path
import uuid, hashlib, jwt, random

JWT_SECRET = "campuscrib-2026"
JWT_ALGORITHM = "HS256"

# ── Models ──

class Listing(BaseModel):
    id: str
    user_id: str
    poster_name: str
    title: str
    description: str
    listing_type: str  # "room", "apartment", "studio", "shared"
    price: float
    price_period: str  # "month", "week", "semester"
    university_id: str
    university_name: str
    address: str
    neighborhood: str
    amenities: list[str] = []
    photos_emoji: list[str] = []
    available_from: str = ""
    available_until: str = ""
    roommates_current: int = 0
    roommates_max: int = 1
    gender_preference: str = "any"  # any, male, female
    pets_allowed: bool = False
    smoking_allowed: bool = False
    likes: int = 0
    comment_count: int = 0
    shares: int = 0
    views: int = 0
    featured: bool = False
    status: str = "active"  # active, rented, expired
    created_at: str = ""

class RoommateAd(BaseModel):
    id: str
    user_id: str
    poster_name: str
    title: str
    description: str
    budget_min: float
    budget_max: float
    university_id: str
    university_name: str
    move_in_date: str
    preferences: list[str] = []
    likes: int = 0
    comment_count: int = 0
    created_at: str = ""

class University(BaseModel):
    id: str
    name: str
    city: str
    state: str
    student_count: int = 0
    listing_count: int = 0

class Comment(BaseModel):
    id: str
    target_type: str  # "listing" or "roommate"
    target_id: str
    user_id: str
    user_name: str
    content: str
    likes: int = 0
    created_at: str = ""

class Message(BaseModel):
    id: str
    from_user_id: str
    from_user_name: str
    to_user_id: str
    to_user_name: str
    listing_id: str = ""
    subject: str
    content: str
    read: bool = False
    created_at: str = ""

class User(BaseModel):
    id: str
    email: str
    name: str
    password_hash: str
    university_id: str = ""
    university_name: str = ""
    bio: str = ""
    year: str = ""  # freshman, sophomore, junior, senior, grad
    liked_listings: list[str] = []
    liked_roommates: list[str] = []
    favorites: list[str] = []
    created_at: str = ""

# ── Store ──

LISTINGS: dict[str, Listing] = {}
ROOMMATE_ADS: dict[str, RoommateAd] = {}
UNIVERSITIES: dict[str, University] = {}
COMMENTS: dict[str, Comment] = {}
MESSAGES: dict[str, Message] = {}
USERS: dict[str, User] = {}
EMAIL_INDEX: dict[str, str] = {}
ACTIVITY_FEED: list[dict] = []

def _hash(pw): return hashlib.sha256(f"cc-{pw}".encode()).hexdigest()

def seed_data():
    # Universities
    unis = [
        ("UC Berkeley", "Berkeley", "CA", 45000),
        ("Stanford University", "Palo Alto", "CA", 17000),
        ("MIT", "Cambridge", "MA", 11500),
        ("NYU", "New York", "NY", 52000),
        ("University of Texas", "Austin", "TX", 51000),
        ("UCLA", "Los Angeles", "CA", 46000),
        ("University of Michigan", "Ann Arbor", "MI", 47000),
        ("Georgia Tech", "Atlanta", "GA", 40000),
    ]
    for i, (name, city, state, students) in enumerate(unis):
        uid = f"uni_{i+1:03d}"
        UNIVERSITIES[uid] = University(id=uid, name=name, city=city, state=state, student_count=students)

    # Listings
    listings_data = [
        ("Sunny Room near Campus", "Bright single room, 5 min walk to campus. Shared kitchen and bathroom.",
         "room", 850, "month", "uni_001", "2380 Bancroft Way", "Southside",
         ["wifi", "laundry", "kitchen", "parking"], ["🛏️", "☀️", "🏠"], 1, 3, "any", False, False, True),
        ("Modern Studio Apartment", "Newly renovated studio with in-unit washer/dryer. Pet-friendly!",
         "studio", 1650, "month", "uni_001", "1920 Oxford St", "Downtown Berkeley",
         ["wifi", "laundry", "gym", "elevator", "pets"], ["🏢", "✨", "🐕"], 0, 1, "any", True, False, False),
        ("Shared Apartment - 1 Room Available", "Looking for 1 roommate in a 3BR/2BA. Great location.",
         "shared", 750, "month", "uni_002", "450 University Ave", "College Terrace",
         ["wifi", "kitchen", "backyard", "bike_storage"], ["🏡", "🌳"], 2, 3, "any", False, False, False),
        ("Cozy Room in Townhouse", "Furnished room in quiet townhouse. Grad students preferred.",
         "room", 1100, "month", "uni_003", "88 Hampshire St", "Kendall Square",
         ["wifi", "furnished", "kitchen", "heating"], ["🏘️", "📚"], 1, 2, "any", False, False, True),
        ("East Village Apartment Share", "Room in a 2BR apartment. Amazing location, subway nearby.",
         "shared", 1400, "month", "uni_004", "321 E 10th St", "East Village",
         ["wifi", "laundry", "subway_nearby", "rooftop"], ["🏙️", "🌆"], 1, 2, "any", False, False, False),
        ("West Campus Studio", "Efficient studio 2 blocks from UT. Bills included!",
         "studio", 950, "month", "uni_005", "2100 San Antonio St", "West Campus",
         ["wifi", "bills_included", "furnished", "pool"], ["🎓", "🏊"], 0, 1, "any", False, False, True),
        ("Westwood Apartment", "Spacious 1BR near UCLA campus. Great for couples or single.",
         "apartment", 1800, "month", "uni_006", "680 Kelton Ave", "Westwood",
         ["wifi", "parking", "gym", "laundry", "balcony"], ["🌴", "🏢"], 0, 2, "any", True, False, False),
        ("Ann Arbor House Room", "Room in a large 5BR student house. Fun social atmosphere!",
         "room", 650, "month", "uni_007", "1025 Oakland Ave", "Burns Park",
         ["wifi", "kitchen", "backyard", "fireplace", "porch"], ["🏠", "🍂", "🎉"], 4, 5, "any", False, False, False),
        ("Midtown Atlanta Loft", "Converted loft space near Georgia Tech. Very unique!",
         "apartment", 1200, "month", "uni_008", "75 5th St NW", "Midtown",
         ["wifi", "exposed_brick", "high_ceilings", "gym"], ["🧱", "🏙️"], 0, 1, "any", False, False, True),
        ("Summer Sublet - Berkeley Hills", "Available June-August. Stunning views!",
         "room", 900, "month", "uni_001", "1455 Grizzly Peak Blvd", "Berkeley Hills",
         ["wifi", "view", "quiet", "nature", "parking"], ["🏔️", "🌅"], 1, 2, "any", False, False, False),
        ("Female-Only House", "Room in all-female student house. Safe, clean, quiet.",
         "room", 800, "month", "uni_004", "412 W 22nd St", "Chelsea",
         ["wifi", "kitchen", "laundry", "safe"], ["🏠", "🔒"], 3, 4, "female", False, False, False),
        ("Pet-Friendly Room, Central Campus", "Your furry friend is welcome! Large room with private bath.",
         "room", 1050, "month", "uni_007", "525 S State St", "Central Campus",
         ["wifi", "private_bath", "pets", "furnished"], ["🐱", "🛏️"], 1, 2, "any", True, False, False),
    ]

    for i, (title, desc, ltype, price, period, uni_id, addr, hood, amenities, photos,
            current, max_rm, gender, pets, smoking, featured) in enumerate(listings_data):
        lid = f"lst_{i+1:03d}"
        uni = UNIVERSITIES[uni_id]
        LISTINGS[lid] = Listing(
            id=lid, user_id=f"seed_user_{i%3}", poster_name=f"Student{i+1}",
            title=title, description=desc, listing_type=ltype, price=price,
            price_period=period, university_id=uni_id, university_name=uni.name,
            address=addr, neighborhood=hood, amenities=amenities, photos_emoji=photos,
            available_from="2026-05-01", available_until="2027-05-01",
            roommates_current=current, roommates_max=max_rm,
            gender_preference=gender, pets_allowed=pets, smoking_allowed=smoking,
            likes=random.randint(5, 200), comment_count=random.randint(2, 30),
            shares=random.randint(0, 50), views=random.randint(100, 5000),
            featured=featured, created_at=(datetime.utcnow() - timedelta(days=random.randint(1, 60))).isoformat(),
        )

    # Update university listing counts
    for uid in UNIVERSITIES:
        UNIVERSITIES[uid].listing_count = sum(1 for l in LISTINGS.values() if l.university_id == uid)

    # Roommate ads
    roommate_data = [
        ("Looking for chill roommate near Berkeley", "Clean, quiet, 420-friendly. Grad student studying CS.",
         800, 1200, "uni_001", "2026-06-01", ["quiet", "clean", "grad_student", "420_friendly"]),
        ("Seeking female roommate - East Village", "Professional student, neat, respectful. No parties.",
         1000, 1500, "uni_004", "2026-05-15", ["female", "clean", "no_parties", "professional"]),
        ("Roommate needed for house in Ann Arbor", "Social, likes cooking, open to hanging out.",
         500, 800, "uni_007", "2026-08-01", ["social", "cooking", "student"]),
        ("MIT area - need quiet study buddy", "Engineering student, need focused environment.",
         900, 1300, "uni_003", "2026-06-15", ["quiet", "studious", "engineering"]),
    ]
    for i, (title, desc, bmin, bmax, uni_id, move_in, prefs) in enumerate(roommate_data):
        rid = f"rmt_{i+1:03d}"
        uni = UNIVERSITIES[uni_id]
        ROOMMATE_ADS[rid] = RoommateAd(
            id=rid, user_id=f"seed_user_{i}", poster_name=f"Student{i+10}",
            title=title, description=desc, budget_min=bmin, budget_max=bmax,
            university_id=uni_id, university_name=uni.name, move_in_date=move_in,
            preferences=prefs, likes=random.randint(3, 50), comment_count=random.randint(1, 15),
            created_at=(datetime.utcnow() - timedelta(days=random.randint(1, 30))).isoformat(),
        )

    # Seed comments
    comment_texts = [
        "Is this still available?", "Looks great! What's the lease term?",
        "Can I schedule a viewing?", "Love the location!",
        "Is parking included?", "How's the noise level?",
        "Are utilities included in the rent?", "This is a steal for that area!",
        "I'm interested! Just sent you a DM.", "What floor is this on?",
    ]
    for lid in list(LISTINGS.keys())[:8]:
        for j in range(random.randint(2, 5)):
            cid = f"cmt_{uuid.uuid4().hex[:8]}"
            COMMENTS[cid] = Comment(
                id=cid, target_type="listing", target_id=lid,
                user_id=f"anon_{j}", user_name=f"Student{random.randint(1,99)}",
                content=random.choice(comment_texts), likes=random.randint(0, 20),
                created_at=(datetime.utcnow() - timedelta(hours=random.randint(1, 500))).isoformat(),
            )

    # Seed messages
    MESSAGES["msg_001"] = Message(
        id="msg_001", from_user_id="seed_user_0", from_user_name="Alex",
        to_user_id="seed_user_1", to_user_name="Jordan", listing_id="lst_001",
        subject="Interested in your room", content="Hi! Is the room on Bancroft still available?",
        created_at=datetime.utcnow().isoformat(),
    )

    # Test users
    for email, pw, name, uni_id, year in [
        ("alex@campus.edu", "room123", "Alex Chen", "uni_001", "junior"),
        ("jordan@campus.edu", "crib456", "Jordan Smith", "uni_004", "senior"),
    ]:
        uid = f"user_{uuid.uuid4().hex[:8]}"
        uni = UNIVERSITIES.get(uni_id, University(id="", name="", city="", state=""))
        USERS[uid] = User(id=uid, email=email, name=name, password_hash=_hash(pw),
                          university_id=uni_id, university_name=uni.name,
                          year=year, created_at=datetime.utcnow().isoformat())
        EMAIL_INDEX[email] = uid

    # Activity feed
    for lid in list(LISTINGS.keys())[:5]:
        l = LISTINGS[lid]
        ACTIVITY_FEED.append({"type": "new_listing", "listing_id": lid, "title": l.title,
                               "poster": l.poster_name, "timestamp": l.created_at})


# ── Auth ──

def create_token(user):
    return jwt.encode({"user_id": user.id, "email": user.email, "name": user.name,
                        "exp": datetime.utcnow() + timedelta(hours=24)},
                       JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    if not authorization: raise HTTPException(401, "Login required")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer": raise HTTPException(401, "Invalid token")
    try:
        payload = jwt.decode(parts[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = USERS.get(payload.get("user_id"))
        if not user: raise HTTPException(401, "User not found")
        return user
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise HTTPException(401, "Invalid or expired token")


# ── App ──

@asynccontextmanager
async def lifespan(app):
    seed_data()
    yield

app = FastAPI(title="CampusCrib", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


# ═══ PUBLIC (10) ═══

@app.get("/api/listings")
def browse_listings(university: Optional[str] = Query(None), listing_type: Optional[str] = Query(None),
                    min_price: Optional[float] = Query(None), max_price: Optional[float] = Query(None),
                    amenity: Optional[str] = Query(None), pets: Optional[bool] = Query(None),
                    gender: Optional[str] = Query(None), q: Optional[str] = Query(None),
                    sort_by: Optional[str] = Query("recent"), page: int = Query(1), per_page: int = Query(10)):
    items = [l for l in LISTINGS.values() if l.status == "active"]
    if university: items = [l for l in items if l.university_id == university]
    if listing_type: items = [l for l in items if l.listing_type == listing_type]
    if min_price is not None: items = [l for l in items if l.price >= min_price]
    if max_price is not None: items = [l for l in items if l.price <= max_price]
    if amenity: items = [l for l in items if amenity in l.amenities]
    if pets is not None: items = [l for l in items if l.pets_allowed == pets]
    if gender: items = [l for l in items if l.gender_preference in [gender, "any"]]
    if q:
        ql = q.lower()
        items = [l for l in items if ql in l.title.lower() or ql in l.description.lower()
                 or ql in l.neighborhood.lower() or ql in l.university_name.lower()]
    if sort_by == "price_asc": items.sort(key=lambda l: l.price)
    elif sort_by == "price_desc": items.sort(key=lambda l: l.price, reverse=True)
    elif sort_by == "popular": items.sort(key=lambda l: l.likes + l.views, reverse=True)
    else: items.sort(key=lambda l: l.created_at, reverse=True)
    total = len(items)
    items = items[(page-1)*per_page : page*per_page]
    return {"listings": [_listing_summary(l) for l in items], "total": total, "page": page,
            "per_page": per_page, "pages": (total + per_page - 1) // per_page}

def _listing_summary(l: Listing) -> dict:
    return {"id": l.id, "title": l.title, "listing_type": l.listing_type, "price": l.price,
            "price_period": l.price_period, "university_name": l.university_name,
            "neighborhood": l.neighborhood, "amenities": l.amenities[:5],
            "photos_emoji": l.photos_emoji[:2], "likes": l.likes, "comment_count": l.comment_count,
            "views": l.views, "featured": l.featured, "poster_name": l.poster_name,
            "available_from": l.available_from, "created_at": l.created_at}

@app.get("/api/listings/featured")
def featured_listings():
    items = [l for l in LISTINGS.values() if l.featured and l.status == "active"]
    return {"listings": [_listing_summary(l) for l in items], "total": len(items)}

@app.get("/api/listings/nearby")
def nearby_listings(university: str = Query(...), radius_miles: int = Query(5)):
    items = [l for l in LISTINGS.values() if l.university_id == university and l.status == "active"]
    return {"listings": [_listing_summary(l) for l in items], "total": len(items), "university": university}

@app.get("/api/listings/{listing_id}")
def get_listing(listing_id: str):
    if listing_id not in LISTINGS: raise HTTPException(404, "Listing not found")
    l = LISTINGS[listing_id]
    l.views += 1
    data = l.model_dump()
    data["university"] = UNIVERSITIES.get(l.university_id, {}).model_dump() if l.university_id in UNIVERSITIES else {}
    return data

@app.get("/api/universities")
def list_universities():
    unis = sorted(UNIVERSITIES.values(), key=lambda u: u.listing_count, reverse=True)
    return {"universities": [u.model_dump() for u in unis], "total": len(unis)}

@app.get("/api/universities/{uni_id}")
def get_university(uni_id: str):
    if uni_id not in UNIVERSITIES: raise HTTPException(404, "University not found")
    uni = UNIVERSITIES[uni_id]
    listings = [_listing_summary(l) for l in LISTINGS.values()
                if l.university_id == uni_id and l.status == "active"]
    return {"university": uni.model_dump(), "listings": listings, "total": len(listings)}

@app.get("/api/roommates")
def browse_roommates(university: Optional[str] = Query(None), q: Optional[str] = Query(None),
                     page: int = Query(1), per_page: int = Query(10)):
    items = list(ROOMMATE_ADS.values())
    if university: items = [r for r in items if r.university_id == university]
    if q:
        ql = q.lower()
        items = [r for r in items if ql in r.title.lower() or ql in r.description.lower()]
    items.sort(key=lambda r: r.created_at, reverse=True)
    total = len(items)
    items = items[(page-1)*per_page : page*per_page]
    return {"roommates": [r.model_dump() for r in items], "total": total, "page": page}

@app.get("/api/roommates/{ad_id}")
def get_roommate_ad(ad_id: str):
    if ad_id not in ROOMMATE_ADS: raise HTTPException(404, "Ad not found")
    return {"roommate_ad": ROOMMATE_ADS[ad_id].model_dump()}

@app.get("/api/search")
def global_search(q: str = Query(...)):
    ql = q.lower()
    listings = [_listing_summary(l) for l in LISTINGS.values()
                if ql in l.title.lower() or ql in l.description.lower() or ql in l.neighborhood.lower()][:10]
    roommates = [r.model_dump() for r in ROOMMATE_ADS.values()
                 if ql in r.title.lower() or ql in r.description.lower()][:5]
    unis = [u.model_dump() for u in UNIVERSITIES.values() if ql in u.name.lower() or ql in u.city.lower()][:5]
    return {"query": q, "listings": listings, "roommates": roommates, "universities": unis,
            "total": len(listings) + len(roommates) + len(unis)}

@app.get("/api/site/info")
def site_info():
    return {"name": "CampusCrib", "tagline": "Find your next student home",
            "listing_count": sum(1 for l in LISTINGS.values() if l.status == "active"),
            "university_count": len(UNIVERSITIES), "user_count": len(USERS),
            "cities": list(set(u.city for u in UNIVERSITIES.values()))}


# ═══ AUTH (2) ═══

class LoginReq(BaseModel):
    email: str
    password: str

class RegisterReq(BaseModel):
    email: str
    password: str
    name: str
    university_id: str = ""
    year: str = ""

@app.post("/api/auth/login")
def login(req: LoginReq):
    uid = EMAIL_INDEX.get(req.email.lower())
    if not uid or USERS[uid].password_hash != _hash(req.password):
        raise HTTPException(401, "Invalid credentials")
    user = USERS[uid]
    return {"token": create_token(user), "user_id": user.id, "name": user.name,
            "email": user.email, "university": user.university_name, "message": f"Welcome back, {user.name}!"}

@app.post("/api/auth/register")
def register(req: RegisterReq):
    if req.email.lower() in EMAIL_INDEX: raise HTTPException(409, "Email already registered")
    if len(req.password) < 6: raise HTTPException(400, "Password too short")
    uid = f"user_{uuid.uuid4().hex[:8]}"
    uni = UNIVERSITIES.get(req.university_id)
    user = User(id=uid, email=req.email.lower(), name=req.name, password_hash=_hash(req.password),
                university_id=req.university_id, university_name=uni.name if uni else "",
                year=req.year, created_at=datetime.utcnow().isoformat())
    USERS[uid] = user
    EMAIL_INDEX[req.email.lower()] = uid
    return {"token": create_token(user), "user_id": uid, "name": req.name, "email": req.email,
            "message": f"Welcome to CampusCrib, {req.name}!"}


# ═══ PROTECTED (23) ═══

@app.get("/api/auth/profile")
def get_profile(user: User = Depends(get_current_user)):
    return {"id": user.id, "name": user.name, "email": user.email,
            "university": user.university_name, "year": user.year,
            "favorites_count": len(user.favorites), "listings_count": sum(1 for l in LISTINGS.values() if l.user_id == user.id)}

class ProfileUpdateReq(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    year: Optional[str] = None

@app.put("/api/auth/profile")
def update_profile(req: ProfileUpdateReq, user: User = Depends(get_current_user)):
    if req.name: user.name = req.name
    if req.bio: user.bio = req.bio
    if req.year: user.year = req.year
    return {"message": "Profile updated", "profile": {"name": user.name, "bio": user.bio, "year": user.year}}

# ── Listing CRUD ──

class CreateListingReq(BaseModel):
    title: str
    description: str
    listing_type: str
    price: float
    price_period: str = "month"
    university_id: str
    address: str
    neighborhood: str = ""
    amenities: list[str] = []
    available_from: str = ""

@app.post("/api/listings")
def create_listing(req: CreateListingReq, user: User = Depends(get_current_user)):
    uni = UNIVERSITIES.get(req.university_id)
    if not uni: raise HTTPException(400, "Invalid university")
    lid = f"lst_{uuid.uuid4().hex[:8]}"
    listing = Listing(
        id=lid, user_id=user.id, poster_name=user.name, title=req.title,
        description=req.description, listing_type=req.listing_type, price=req.price,
        price_period=req.price_period, university_id=req.university_id, university_name=uni.name,
        address=req.address, neighborhood=req.neighborhood, amenities=req.amenities,
        available_from=req.available_from, created_at=datetime.utcnow().isoformat(),
    )
    LISTINGS[lid] = listing
    return {"listing": _listing_summary(listing), "message": f"Listing '{req.title}' posted!"}

class UpdateListingReq(BaseModel):
    title: Optional[str] = None
    price: Optional[float] = None
    status: Optional[str] = None

@app.put("/api/listings/{listing_id}")
def update_listing(listing_id: str, req: UpdateListingReq, user: User = Depends(get_current_user)):
    if listing_id not in LISTINGS: raise HTTPException(404, "Listing not found")
    l = LISTINGS[listing_id]
    if l.user_id != user.id: raise HTTPException(403, "Not your listing")
    if req.title: l.title = req.title
    if req.price: l.price = req.price
    if req.status: l.status = req.status
    return {"listing": _listing_summary(l), "message": "Listing updated"}

@app.delete("/api/listings/{listing_id}")
def delete_listing(listing_id: str, user: User = Depends(get_current_user)):
    if listing_id not in LISTINGS: raise HTTPException(404, "Listing not found")
    if LISTINGS[listing_id].user_id != user.id: raise HTTPException(403, "Not your listing")
    del LISTINGS[listing_id]
    return {"message": "Listing deleted"}

# ── Social actions on listings ──

@app.post("/api/listings/{listing_id}/like")
def like_listing(listing_id: str, user: User = Depends(get_current_user)):
    if listing_id not in LISTINGS: raise HTTPException(404, "Not found")
    if listing_id in user.liked_listings: raise HTTPException(400, "Already liked")
    user.liked_listings.append(listing_id)
    LISTINGS[listing_id].likes += 1
    return {"liked": True, "total_likes": LISTINGS[listing_id].likes}

@app.post("/api/listings/{listing_id}/unlike")
def unlike_listing(listing_id: str, user: User = Depends(get_current_user)):
    if listing_id not in LISTINGS: raise HTTPException(404, "Not found")
    user.liked_listings = [l for l in user.liked_listings if l != listing_id]
    LISTINGS[listing_id].likes = max(0, LISTINGS[listing_id].likes - 1)
    return {"liked": False, "total_likes": LISTINGS[listing_id].likes}

@app.get("/api/listings/{listing_id}/comments")
def get_listing_comments(listing_id: str, user: User = Depends(get_current_user)):
    if listing_id not in LISTINGS: raise HTTPException(404, "Not found")
    comments = [c.model_dump() for c in COMMENTS.values() if c.target_id == listing_id]
    return {"comments": comments, "total": len(comments)}

class CommentReq(BaseModel):
    content: str

@app.post("/api/listings/{listing_id}/comments")
def comment_on_listing(listing_id: str, req: CommentReq, user: User = Depends(get_current_user)):
    if listing_id not in LISTINGS: raise HTTPException(404, "Not found")
    cid = f"cmt_{uuid.uuid4().hex[:8]}"
    comment = Comment(id=cid, target_type="listing", target_id=listing_id,
                      user_id=user.id, user_name=user.name, content=req.content,
                      created_at=datetime.utcnow().isoformat())
    COMMENTS[cid] = comment
    LISTINGS[listing_id].comment_count += 1
    return {"comment": comment.model_dump(), "message": "Comment posted!"}

@app.post("/api/listings/{listing_id}/share")
def share_listing(listing_id: str, user: User = Depends(get_current_user)):
    if listing_id not in LISTINGS: raise HTTPException(404, "Not found")
    LISTINGS[listing_id].shares += 1
    return {"shared": True, "total_shares": LISTINGS[listing_id].shares}

@app.post("/api/listings/{listing_id}/report")
def report_listing(listing_id: str, user: User = Depends(get_current_user)):
    if listing_id not in LISTINGS: raise HTTPException(404, "Not found")
    return {"reported": True, "message": "Thank you for reporting. We'll review this listing."}

# ── Roommate ads ──

class CreateRoommateReq(BaseModel):
    title: str
    description: str
    budget_min: float
    budget_max: float
    university_id: str
    move_in_date: str
    preferences: list[str] = []

@app.post("/api/roommates")
def create_roommate_ad(req: CreateRoommateReq, user: User = Depends(get_current_user)):
    uni = UNIVERSITIES.get(req.university_id)
    rid = f"rmt_{uuid.uuid4().hex[:8]}"
    ad = RoommateAd(id=rid, user_id=user.id, poster_name=user.name,
                    title=req.title, description=req.description,
                    budget_min=req.budget_min, budget_max=req.budget_max,
                    university_id=req.university_id, university_name=uni.name if uni else "",
                    move_in_date=req.move_in_date, preferences=req.preferences,
                    created_at=datetime.utcnow().isoformat())
    ROOMMATE_ADS[rid] = ad
    return {"roommate_ad": ad.model_dump(), "message": f"Roommate ad posted!"}

@app.post("/api/roommates/{ad_id}/like")
def like_roommate_ad(ad_id: str, user: User = Depends(get_current_user)):
    if ad_id not in ROOMMATE_ADS: raise HTTPException(404, "Not found")
    ROOMMATE_ADS[ad_id].likes += 1
    return {"liked": True, "total_likes": ROOMMATE_ADS[ad_id].likes}

@app.post("/api/roommates/{ad_id}/comments")
def comment_on_roommate_ad(ad_id: str, req: CommentReq, user: User = Depends(get_current_user)):
    if ad_id not in ROOMMATE_ADS: raise HTTPException(404, "Not found")
    cid = f"cmt_{uuid.uuid4().hex[:8]}"
    comment = Comment(id=cid, target_type="roommate", target_id=ad_id,
                      user_id=user.id, user_name=user.name, content=req.content,
                      created_at=datetime.utcnow().isoformat())
    COMMENTS[cid] = comment
    return {"comment": comment.model_dump(), "message": "Comment posted!"}

# ── Messages ──

class SendMessageReq(BaseModel):
    to_user_id: str
    subject: str
    content: str
    listing_id: str = ""

@app.get("/api/messages")
def get_inbox(user: User = Depends(get_current_user)):
    msgs = [m.model_dump() for m in MESSAGES.values() if m.to_user_id == user.id or m.from_user_id == user.id]
    msgs.sort(key=lambda m: m["created_at"], reverse=True)
    return {"messages": msgs, "total": len(msgs)}

@app.post("/api/messages")
def send_message(req: SendMessageReq, user: User = Depends(get_current_user)):
    mid = f"msg_{uuid.uuid4().hex[:8]}"
    msg = Message(id=mid, from_user_id=user.id, from_user_name=user.name,
                  to_user_id=req.to_user_id, to_user_name="User",
                  listing_id=req.listing_id, subject=req.subject, content=req.content,
                  created_at=datetime.utcnow().isoformat())
    MESSAGES[mid] = msg
    return {"message": msg.model_dump(), "status": "sent"}

@app.get("/api/messages/{message_id}")
def get_message(message_id: str, user: User = Depends(get_current_user)):
    if message_id not in MESSAGES: raise HTTPException(404, "Message not found")
    msg = MESSAGES[message_id]
    if msg.to_user_id == user.id: msg.read = True
    return {"message": msg.model_dump()}

# ── Favorites ──

class FavoriteReq(BaseModel):
    listing_id: str

@app.get("/api/favorites")
def get_favorites(user: User = Depends(get_current_user)):
    items = [_listing_summary(LISTINGS[lid]) for lid in user.favorites if lid in LISTINGS]
    return {"favorites": items, "total": len(items)}

@app.post("/api/favorites/add")
def add_favorite(req: FavoriteReq, user: User = Depends(get_current_user)):
    if req.listing_id in user.favorites: raise HTTPException(400, "Already saved")
    user.favorites.append(req.listing_id)
    return {"saved": True, "total_favorites": len(user.favorites)}

@app.post("/api/favorites/remove")
def remove_favorite(req: FavoriteReq, user: User = Depends(get_current_user)):
    user.favorites = [f for f in user.favorites if f != req.listing_id]
    return {"saved": False, "total_favorites": len(user.favorites)}

# ── Feed & User content ──

@app.get("/api/feed")
def activity_feed(user: User = Depends(get_current_user)):
    return {"feed": ACTIVITY_FEED[-20:], "total": len(ACTIVITY_FEED)}

@app.get("/api/me/listings")
def my_listings(user: User = Depends(get_current_user)):
    items = [_listing_summary(l) for l in LISTINGS.values() if l.user_id == user.id]
    return {"listings": items, "total": len(items)}

@app.get("/api/notifications")
def get_notifications(user: User = Depends(get_current_user)):
    return {"notifications": [], "total": 0, "unread": 0}

# ── SPA ──
@app.get("/", response_class=HTMLResponse)
def serve_spa():
    return HTMLResponse(content="<h1>🏠 CampusCrib</h1><p>Student Housing Board. API at /api/listings</p>")
