"""
Restaurant Simulation — "La Terminal"

A realistic restaurant site with:
- Menu browsing (categories, items, dietary filters)
- Table reservations (date, time, party size, special requests)
- Online ordering (pickup/delivery)
- No OpenAPI/Swagger exposed (docs_url=None, redoc_url=None)
- Auth required for reservations and orders

This simulates a real restaurant website where:
- A developer built it quickly with FastAPI but didn't expose docs
- The frontend is a React SPA
- The API is undocumented
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date, timedelta
from pathlib import Path
import uuid
import hashlib
import jwt

# ── Config ──
JWT_SECRET = "la-terminal-secret"
JWT_ALGORITHM = "HS256"

# ── Models ──

class MenuItem(BaseModel):
    id: str
    name: str
    description: str
    price: float
    category: str  # appetizers, mains, desserts, drinks, sides
    dietary: list[str] = []  # vegetarian, vegan, gluten_free, spicy
    available: bool = True
    popular: bool = False
    image_emoji: str = ""


class TableSlot(BaseModel):
    id: str
    date: str
    time: str
    party_size_min: int = 1
    party_size_max: int = 8
    available: bool = True


class Reservation(BaseModel):
    id: str
    user_id: str
    date: str
    time: str
    party_size: int
    name: str
    phone: str
    special_requests: str = ""
    status: str = "confirmed"  # confirmed, cancelled
    created_at: str = ""


class OrderItem(BaseModel):
    menu_item_id: str
    quantity: int
    notes: str = ""


class Order(BaseModel):
    id: str
    user_id: str
    items: list[dict] = []
    subtotal: float = 0
    tax: float = 0
    total: float = 0
    order_type: str = "pickup"  # pickup, delivery
    delivery_address: str = ""
    status: str = "pending"  # pending, preparing, ready, delivered, cancelled
    created_at: str = ""


class User(BaseModel):
    id: str
    email: str
    name: str
    password_hash: str
    phone: str = ""


# ── In-Memory Store ──

MENU: dict[str, MenuItem] = {}
RESERVATIONS: dict[str, Reservation] = {}
ORDERS: dict[str, Order] = {}
USERS: dict[str, User] = {}
EMAIL_INDEX: dict[str, str] = {}
TIME_SLOTS: list[str] = ["11:30", "12:00", "12:30", "13:00", "13:30",
                          "18:00", "18:30", "19:00", "19:30", "20:00", "20:30", "21:00"]


def _hash(pw): return hashlib.sha256(f"salt-{pw}".encode()).hexdigest()


def seed_data():
    """Populate menu and test users."""
    items = [
        # Appetizers
        ("Crispy Calamari", "Lightly battered with marinara and lemon aioli", 14.99, "appetizers", [], True, "🦑"),
        ("Bruschetta Trio", "Tomato basil, mushroom truffle, olive tapenade", 12.99, "appetizers", ["vegetarian"], False, "🍅"),
        ("Spicy Tuna Tartare", "With avocado, sesame, and wonton chips", 16.99, "appetizers", ["gluten_free", "spicy"], True, "🐟"),
        ("Caesar Salad", "Romaine, parmesan, croutons, house dressing", 11.99, "appetizers", ["vegetarian"], False, "🥗"),

        # Mains
        ("Grilled Salmon", "Atlantic salmon with roasted vegetables and dill sauce", 28.99, "mains", ["gluten_free"], True, "🐟"),
        ("Filet Mignon", "8oz prime beef with truffle mashed potatoes", 42.99, "mains", ["gluten_free"], True, "🥩"),
        ("Mushroom Risotto", "Arborio rice with wild mushrooms and parmesan", 22.99, "mains", ["vegetarian", "gluten_free"], False, "🍄"),
        ("Pad Thai", "Rice noodles with shrimp, peanuts, and lime", 19.99, "mains", ["spicy"], False, "🍜"),
        ("Beyond Burger", "Plant-based patty with all the fixings", 17.99, "mains", ["vegan"], False, "🍔"),
        ("Lobster Pasta", "Fresh linguine with butter-poached lobster", 36.99, "mains", [], True, "🦞"),

        # Desserts
        ("Tiramisu", "Classic Italian coffee-flavored layers", 12.99, "desserts", ["vegetarian"], True, "🍰"),
        ("Chocolate Lava Cake", "Warm center with vanilla ice cream", 14.99, "desserts", ["vegetarian"], False, "🍫"),
        ("Mango Sorbet", "Three scoops of house-made tropical sorbet", 8.99, "desserts", ["vegan", "gluten_free"], False, "🥭"),

        # Drinks
        ("House Red Wine", "Glass of Cabernet Sauvignon", 12.99, "drinks", ["vegan", "gluten_free"], False, "🍷"),
        ("Craft IPA", "Local brewery, 16oz", 8.99, "drinks", ["vegan"], False, "🍺"),
        ("Espresso Martini", "Vodka, coffee liqueur, fresh espresso", 15.99, "drinks", [], True, "🍸"),
        ("Fresh Lemonade", "House-made with mint", 4.99, "drinks", ["vegan", "gluten_free"], False, "🍋"),

        # Sides
        ("Truffle Fries", "With parmesan and rosemary", 9.99, "sides", ["vegetarian", "gluten_free"], True, "🍟"),
        ("Grilled Asparagus", "With lemon butter", 8.99, "sides", ["vegan", "gluten_free"], False, "🌿"),
        ("Mac & Cheese", "Three-cheese blend with breadcrumb crust", 10.99, "sides", ["vegetarian"], False, "🧀"),
    ]

    for i, (name, desc, price, cat, dietary, popular, emoji) in enumerate(items):
        mid = f"item_{i+1:03d}"
        MENU[mid] = MenuItem(
            id=mid, name=name, description=desc, price=price,
            category=cat, dietary=dietary, popular=popular, image_emoji=emoji,
        )

    # Test users
    for email, pw, name, phone in [
        ("maria@email.com", "dinner123", "Maria Garcia", "+1-555-0101"),
        ("james@email.com", "table456", "James Wilson", "+1-555-0202"),
    ]:
        uid = f"user_{uuid.uuid4().hex[:8]}"
        USERS[uid] = User(id=uid, email=email, name=name, password_hash=_hash(pw), phone=phone)
        EMAIL_INDEX[email] = uid


# ── Auth helpers ──

def create_token(user):
    return jwt.encode({"user_id": user.id, "email": user.email, "name": user.name,
                        "exp": datetime.utcnow() + timedelta(hours=24)},
                       JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    if not authorization:
        raise HTTPException(status_code=401, detail="Login required")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid token format")
    try:
        payload = jwt.decode(parts[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = USERS.get(payload.get("user_id"))
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── App — NO OpenAPI docs exposed ──

@asynccontextmanager
async def lifespan(app):
    seed_data()
    yield

app = FastAPI(
    title="La Terminal Restaurant",
    docs_url=None,      # No Swagger UI
    redoc_url=None,     # No ReDoc
    openapi_url=None,   # No OpenAPI spec!
    lifespan=lifespan,
)


# ── Public Endpoints ──

@app.get("/api/menu")
def get_menu(
    category: Optional[str] = Query(None),
    dietary: Optional[str] = Query(None),
    popular: Optional[bool] = Query(None),
    q: Optional[str] = Query(None),
):
    """Browse the menu."""
    items = list(MENU.values())
    if category:
        items = [i for i in items if i.category == category]
    if dietary:
        items = [i for i in items if dietary in i.dietary]
    if popular is not None:
        items = [i for i in items if i.popular == popular]
    if q:
        q_lower = q.lower()
        items = [i for i in items if q_lower in i.name.lower() or q_lower in i.description.lower()]
    return {
        "items": [i.model_dump() for i in items],
        "total": len(items),
        "categories": list(set(i.category for i in MENU.values())),
    }


@app.get("/api/menu/{item_id}")
def get_menu_item(item_id: str):
    """Get menu item detail."""
    if item_id not in MENU:
        raise HTTPException(status_code=404, detail="Item not found")
    return MENU[item_id].model_dump()


@app.get("/api/availability")
def check_availability(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    party_size: Optional[int] = Query(None),
):
    """Check table availability for a date."""
    target_date = date or (datetime.now().date() + timedelta(days=1)).isoformat()

    # Generate available slots
    slots = []
    for time in TIME_SLOTS:
        # Some slots are "taken" based on hash to simulate real availability
        slot_hash = hashlib.md5(f"{target_date}-{time}".encode()).hexdigest()
        taken = int(slot_hash[:2], 16) < 60  # ~23% chance taken
        max_party = 8 if int(slot_hash[2:4], 16) > 100 else 4
        available = not taken and (party_size is None or party_size <= max_party)
        slots.append({
            "date": target_date,
            "time": time,
            "available": available,
            "max_party_size": max_party,
        })
    return {"date": target_date, "slots": slots}


@app.get("/api/restaurant/info")
def restaurant_info():
    """Restaurant details."""
    return {
        "name": "La Terminal",
        "cuisine": "Contemporary American with global influences",
        "address": "456 Railway Ave, San Francisco, CA 94105",
        "phone": "+1-415-555-FOOD",
        "hours": {"mon-thu": "11:30-22:00", "fri-sat": "11:30-23:00", "sun": "10:00-21:00"},
        "price_range": "$$-$$$",
        "rating": 4.6,
        "review_count": 847,
    }


# ── Auth Endpoints ──

class LoginReq(BaseModel):
    email: str
    password: str

class RegisterReq(BaseModel):
    email: str
    password: str
    name: str
    phone: str = ""

@app.post("/api/auth/login")
def login(req: LoginReq):
    uid = EMAIL_INDEX.get(req.email.lower())
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = USERS[uid]
    if user.password_hash != _hash(req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": create_token(user), "user_id": user.id, "name": user.name, "email": user.email,
            "message": f"Welcome, {user.name}!"}

@app.post("/api/auth/register")
def register(req: RegisterReq):
    if req.email.lower() in EMAIL_INDEX:
        raise HTTPException(status_code=409, detail="Email already registered")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password too short")
    uid = f"user_{uuid.uuid4().hex[:8]}"
    user = User(id=uid, email=req.email.lower(), name=req.name, password_hash=_hash(req.password), phone=req.phone)
    USERS[uid] = user
    EMAIL_INDEX[req.email.lower()] = uid
    return {"token": create_token(user), "user_id": uid, "name": req.name, "email": req.email,
            "message": f"Account created for {req.name}!"}


# ── Protected: Reservations ──

class ReservationReq(BaseModel):
    date: str
    time: str
    party_size: int
    name: str
    phone: str
    special_requests: str = ""

@app.post("/api/reservations")
def make_reservation(req: ReservationReq, user: User = Depends(get_current_user)):
    """Book a table."""
    if req.party_size < 1 or req.party_size > 8:
        raise HTTPException(status_code=400, detail="Party size must be 1-8")
    try:
        res_date = datetime.strptime(req.date, "%Y-%m-%d").date()
        if res_date < datetime.now().date():
            raise HTTPException(status_code=400, detail="Cannot book in the past")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")
    if req.time not in TIME_SLOTS:
        raise HTTPException(status_code=400, detail=f"Invalid time. Available: {TIME_SLOTS}")

    rid = f"res_{uuid.uuid4().hex[:8]}"
    reservation = Reservation(
        id=rid, user_id=user.id, date=req.date, time=req.time,
        party_size=req.party_size, name=req.name, phone=req.phone,
        special_requests=req.special_requests,
        created_at=datetime.utcnow().isoformat(),
    )
    RESERVATIONS[rid] = reservation
    return {"reservation": reservation.model_dump(),
            "message": f"Table for {req.party_size} confirmed at {req.time} on {req.date}!"}


@app.get("/api/reservations/{res_id}")
def get_reservation(res_id: str, user: User = Depends(get_current_user)):
    if res_id not in RESERVATIONS:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return {"reservation": RESERVATIONS[res_id].model_dump()}


@app.post("/api/reservations/{res_id}/cancel")
def cancel_reservation(res_id: str, user: User = Depends(get_current_user)):
    if res_id not in RESERVATIONS:
        raise HTTPException(status_code=404, detail="Reservation not found")
    RESERVATIONS[res_id].status = "cancelled"
    return {"reservation": RESERVATIONS[res_id].model_dump(), "message": "Reservation cancelled"}


# ── Protected: Orders ──

class OrderReq(BaseModel):
    items: list[dict]  # [{menu_item_id, quantity, notes}]
    order_type: str = "pickup"
    delivery_address: str = ""

@app.post("/api/orders")
def place_order(req: OrderReq, user: User = Depends(get_current_user)):
    """Place a food order."""
    if not req.items:
        raise HTTPException(status_code=400, detail="No items in order")
    if req.order_type == "delivery" and not req.delivery_address:
        raise HTTPException(status_code=400, detail="Delivery address required")

    order_items = []
    subtotal = 0
    for item in req.items:
        menu_item = MENU.get(item.get("menu_item_id"))
        if not menu_item:
            raise HTTPException(status_code=404, detail=f"Menu item {item.get('menu_item_id')} not found")
        if not menu_item.available:
            raise HTTPException(status_code=400, detail=f"{menu_item.name} is not available")
        qty = item.get("quantity", 1)
        line_total = round(menu_item.price * qty, 2)
        subtotal += line_total
        order_items.append({
            "menu_item_id": menu_item.id, "name": menu_item.name,
            "price": menu_item.price, "quantity": qty,
            "notes": item.get("notes", ""), "line_total": line_total,
        })

    tax = round(subtotal * 0.0875, 2)
    total = round(subtotal + tax, 2)

    oid = f"ord_{uuid.uuid4().hex[:8]}"
    order = Order(
        id=oid, user_id=user.id, items=order_items,
        subtotal=subtotal, tax=tax, total=total,
        order_type=req.order_type, delivery_address=req.delivery_address,
        status="pending", created_at=datetime.utcnow().isoformat(),
    )
    ORDERS[oid] = order
    return {"order": order.model_dump(),
            "message": f"Order {oid} placed! Total: ${total}. Status: pending."}


@app.get("/api/orders/{order_id}")
def get_order(order_id: str, user: User = Depends(get_current_user)):
    if order_id not in ORDERS:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"order": ORDERS[order_id].model_dump()}


# ── SPA Frontend ──

@app.get("/", response_class=HTMLResponse)
def serve_spa():
    spa_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if spa_path.exists():
        return HTMLResponse(content=spa_path.read_text())
    return HTMLResponse(content="""<!DOCTYPE html>
<html><body style="font-family:sans-serif;text-align:center;padding:60px">
<h1>🍽️ La Terminal</h1>
<p>Restaurant SPA not built yet. API is at /api/menu</p>
</body></html>""")
