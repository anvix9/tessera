"""
FreshMart Supermarket — Complex E-commerce Simulation

Complexity:
- 8 aisles with 40+ products
- Product variants (sizes, weights)
- Weekly promotions with popup-style discounts
- Loyalty points system
- Coupons/promo codes
- Cart with auto-applied promotions
- Delivery time slots
- Order with pickup/delivery
- Auth + loyalty card
- No OpenAPI spec exposed

Endpoints (25 total):
  PUBLIC (8):
    GET  /api/aisles                     - List all aisles
    GET  /api/aisles/{id}                - Aisle detail with products
    GET  /api/products                   - Search products across aisles
    GET  /api/products/{id}              - Product detail with variants
    GET  /api/promotions                 - Current weekly promotions
    GET  /api/promotions/{id}            - Promotion detail
    GET  /api/store/info                 - Store hours, location, delivery zones
    GET  /api/delivery-slots             - Available delivery time slots

  AUTH (2):
    POST /api/auth/register              - Create account + loyalty card
    POST /api/auth/login                 - Login

  PROTECTED (15):
    GET  /api/auth/profile               - Profile + loyalty points
    POST /api/cart                       - Create cart
    GET  /api/cart/{id}                  - View cart (auto-applies promos)
    POST /api/cart/{id}/add              - Add item to cart
    POST /api/cart/{id}/update           - Update item qty
    POST /api/cart/{id}/remove           - Remove item
    POST /api/cart/{id}/coupon           - Apply coupon code
    DELETE /api/cart/{id}/coupon         - Remove coupon
    POST /api/checkout                   - Place order
    GET  /api/orders                     - Order history
    GET  /api/orders/{id}                - Order detail + tracking
    GET  /api/loyalty                    - Loyalty points balance
    GET  /api/loyalty/history            - Points transaction history
    POST /api/loyalty/redeem             - Redeem points for discount
    GET  /api/favorites                  - Saved favorite products
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date, timedelta
from pathlib import Path
import uuid, hashlib, jwt, random

# ── Config ──
JWT_SECRET = "freshmart-secret-2026"
JWT_ALGORITHM = "HS256"

# ── Models ──

class Aisle(BaseModel):
    id: str
    name: str
    icon: str
    description: str
    product_count: int = 0

class ProductVariant(BaseModel):
    id: str
    label: str  # "500g", "1kg", "6-pack"
    price: float
    unit: str  # "each", "kg", "pack"
    in_stock: bool = True

class Product(BaseModel):
    id: str
    name: str
    brand: str
    aisle_id: str
    description: str
    base_price: float
    unit: str
    image_emoji: str
    tags: list[str] = []
    organic: bool = False
    variants: list[ProductVariant] = []
    rating: float = 4.0
    review_count: int = 0

class Promotion(BaseModel):
    id: str
    title: str
    description: str
    discount_type: str  # "percentage", "fixed", "bogo", "bundle"
    discount_value: float
    product_ids: list[str] = []
    aisle_ids: list[str] = []
    min_purchase: float = 0
    code: str = ""
    active: bool = True
    valid_until: str = ""
    popup: bool = False  # Shows as popup on site

class CartItem(BaseModel):
    product_id: str
    variant_id: Optional[str] = None
    quantity: int
    notes: str = ""

class Cart(BaseModel):
    id: str
    user_id: str
    items: list[CartItem] = []
    coupon_code: str = ""
    created_at: str = ""

class Order(BaseModel):
    id: str
    user_id: str
    items: list[dict] = []
    subtotal: float = 0
    discount: float = 0
    tax: float = 0
    total: float = 0
    loyalty_points_earned: int = 0
    order_type: str = "pickup"
    delivery_address: str = ""
    delivery_slot: str = ""
    status: str = "confirmed"
    created_at: str = ""

class User(BaseModel):
    id: str
    email: str
    name: str
    password_hash: str
    phone: str = ""
    loyalty_card: str = ""
    loyalty_points: int = 0
    favorites: list[str] = []

class LoyaltyTransaction(BaseModel):
    id: str
    user_id: str
    points: int
    type: str  # "earned", "redeemed"
    description: str
    created_at: str

# ── Store ──

AISLES: dict[str, Aisle] = {}
PRODUCTS: dict[str, Product] = {}
PROMOTIONS: dict[str, Promotion] = {}
CARTS: dict[str, Cart] = {}
ORDERS: dict[str, Order] = {}
USERS: dict[str, User] = {}
EMAIL_INDEX: dict[str, str] = {}
LOYALTY_HISTORY: list[LoyaltyTransaction] = []

def _hash(pw): return hashlib.sha256(f"fm-{pw}".encode()).hexdigest()

def seed_data():
    aisles_data = [
        ("produce", "Fresh Produce", "🥬", "Fresh fruits, vegetables, and herbs"),
        ("dairy", "Dairy & Eggs", "🥛", "Milk, cheese, yogurt, eggs, and butter"),
        ("bakery", "Bakery", "🍞", "Fresh bread, pastries, and cakes"),
        ("meat", "Meat & Seafood", "🥩", "Fresh and frozen meats, poultry, and fish"),
        ("frozen", "Frozen Foods", "🧊", "Frozen meals, vegetables, ice cream"),
        ("beverages", "Beverages", "🥤", "Water, juices, sodas, coffee, and tea"),
        ("snacks", "Snacks & Candy", "🍿", "Chips, cookies, chocolate, and nuts"),
        ("household", "Household & Cleaning", "🧹", "Cleaning supplies, paper goods, storage"),
    ]
    for aid, name, icon, desc in aisles_data:
        AISLES[aid] = Aisle(id=aid, name=name, icon=icon, description=desc)

    products_data = [
        # Produce
        ("Organic Bananas", "Nature's Best", "produce", "Ripe organic bananas", 0.79, "lb", "🍌", ["fruit","organic"], True,
         [("bunch_5", "5-pack", 3.49, "pack"), ("single", "Single", 0.79, "each")]),
        ("Avocados", "Green Valley", "produce", "Hass avocados, ready to eat", 1.99, "each", "🥑", ["fruit"], False,
         [("single", "Single", 1.99, "each"), ("bag_4", "Bag of 4", 5.99, "bag")]),
        ("Baby Spinach", "Fresh Fields", "produce", "Pre-washed baby spinach", 3.99, "bag", "🥬", ["vegetable","organic","salad"], True,
         [("5oz", "5oz bag", 3.99, "bag"), ("16oz", "16oz container", 6.99, "container")]),
        ("Roma Tomatoes", "Sun Harvest", "produce", "Vine-ripened roma tomatoes", 2.49, "lb", "🍅", ["vegetable"], False, []),
        ("Fresh Strawberries", "Berry Best", "produce", "Sweet California strawberries", 4.99, "container", "🍓", ["fruit","berries"], False,
         [("1lb", "1lb container", 4.99, "container"), ("2lb", "2lb container", 8.99, "container")]),
        # Dairy
        ("Whole Milk", "Horizon", "dairy", "Organic whole milk", 4.99, "gallon", "🥛", ["organic","milk"], True,
         [("half_gal", "Half Gallon", 3.49, "half_gal"), ("gallon", "Gallon", 4.99, "gallon")]),
        ("Free Range Eggs", "Happy Hens", "dairy", "Large free-range brown eggs", 5.49, "dozen", "🥚", ["organic","eggs"], True,
         [("6pk", "6-pack", 3.29, "pack"), ("12pk", "Dozen", 5.49, "dozen"), ("18pk", "18-pack", 7.99, "pack")]),
        ("Greek Yogurt", "Chobani", "dairy", "Plain non-fat Greek yogurt", 1.29, "cup", "🥛", ["yogurt","protein"], False,
         [("single", "Single cup", 1.29, "cup"), ("32oz", "32oz tub", 5.99, "tub")]),
        ("Cheddar Cheese", "Tillamook", "dairy", "Sharp cheddar cheese block", 6.99, "block", "🧀", ["cheese"], False,
         [("8oz", "8oz block", 4.49, "block"), ("16oz", "1lb block", 6.99, "block"), ("shred", "Shredded 8oz", 4.99, "bag")]),
        ("Butter", "Kerrygold", "dairy", "Pure Irish butter, unsalted", 5.99, "block", "🧈", ["butter","organic"], True, []),
        # Bakery
        ("Sourdough Bread", "La Boulangerie", "bakery", "Artisan sourdough loaf", 5.49, "loaf", "🍞", ["bread","artisan"], False, []),
        ("Croissants", "French Corner", "bakery", "Butter croissants, 4-pack", 6.99, "pack", "🥐", ["pastry"], False,
         [("4pk", "4-pack", 6.99, "pack"), ("single", "Single", 2.49, "each")]),
        ("Chocolate Chip Cookies", "Sweet Home", "bakery", "Fresh-baked cookies", 4.99, "pack", "🍪", ["cookies","sweet"], False, []),
        # Meat
        ("Chicken Breast", "Farm Fresh", "meat", "Boneless skinless chicken breast", 8.99, "lb", "🍗", ["poultry","protein"], False,
         [("1lb", "1 lb", 8.99, "lb"), ("3lb_pack", "Family pack 3lb", 23.99, "pack")]),
        ("Ground Beef 85/15", "Black Angus", "meat", "Ground beef 85% lean", 7.99, "lb", "🥩", ["beef","protein"], False,
         [("1lb", "1 lb", 7.99, "lb"), ("2lb", "2 lb", 14.99, "pack")]),
        ("Atlantic Salmon", "Ocean Catch", "meat", "Fresh Atlantic salmon fillets", 12.99, "lb", "🐟", ["seafood","fish","omega3"], False,
         [("8oz", "8oz fillet", 8.99, "fillet"), ("1lb", "1 lb", 12.99, "lb")]),
        # Frozen
        ("Frozen Pizza", "DiGiorno", "frozen", "Rising crust pepperoni pizza", 7.49, "pizza", "🍕", ["pizza","frozen_meal"], False, []),
        ("Ice Cream", "Ben & Jerry's", "frozen", "Cherry Garcia pint", 5.99, "pint", "🍦", ["dessert","ice_cream"], False,
         [("pint", "Pint", 5.99, "pint"), ("mini", "Mini cup 4-pack", 6.49, "pack")]),
        ("Frozen Vegetables", "Green Giant", "frozen", "Mixed vegetables steamable bag", 2.99, "bag", "🥦", ["vegetable","healthy"], False,
         [("12oz", "12oz bag", 2.99, "bag"), ("24oz", "24oz bag", 4.99, "bag")]),
        # Beverages
        ("Sparkling Water", "LaCroix", "beverages", "Lime sparkling water", 5.49, "12pack", "🥤", ["water","sparkling"], False,
         [("single", "Single can", 0.99, "can"), ("12pk", "12-pack", 5.49, "pack"), ("24pk", "24-pack", 9.99, "pack")]),
        ("Orange Juice", "Tropicana", "beverages", "100% pure squeezed OJ", 4.49, "carton", "🍊", ["juice","vitamin_c"], False,
         [("small", "52oz carton", 4.49, "carton"), ("large", "89oz carton", 6.99, "carton")]),
        ("Cold Brew Coffee", "Stumptown", "beverages", "Original cold brew concentrate", 10.99, "bottle", "☕", ["coffee","cold_brew"], False, []),
        # Snacks
        ("Tortilla Chips", "Tostitos", "snacks", "Restaurant style tortilla chips", 4.49, "bag", "🌮", ["chips","party"], False,
         [("10oz", "10oz bag", 4.49, "bag"), ("18oz", "Party size", 6.99, "bag")]),
        ("Mixed Nuts", "Planters", "snacks", "Deluxe mixed nuts, lightly salted", 9.99, "can", "🥜", ["nuts","protein","snack"], False,
         [("8oz", "8oz can", 6.99, "can"), ("16oz", "1lb can", 9.99, "can")]),
        ("Dark Chocolate", "Lindt", "snacks", "70% cocoa dark chocolate bar", 3.99, "bar", "🍫", ["chocolate","dark"], False, []),
        # Household
        ("Paper Towels", "Bounty", "household", "Select-a-size paper towels", 12.99, "pack", "🧻", ["paper","cleaning"], False,
         [("single", "Single roll", 2.49, "roll"), ("6pk", "6-pack", 12.99, "pack"), ("12pk", "12-pack", 22.99, "pack")]),
        ("Dish Soap", "Dawn", "household", "Ultra concentrated dish soap", 3.99, "bottle", "🧴", ["cleaning","kitchen"], False, []),
        ("Trash Bags", "Glad", "household", "ForceFlex tall kitchen bags", 11.99, "box", "🗑️", ["trash","kitchen"], False,
         [("25ct", "25 count", 7.99, "box"), ("50ct", "50 count", 11.99, "box"), ("100ct", "100 count", 19.99, "box")]),
    ]

    for i, (name, brand, aisle, desc, price, unit, emoji, tags, organic, variants_data) in enumerate(products_data):
        pid = f"prod_{i+1:03d}"
        variants = []
        for j, v in enumerate(variants_data):
            vid = f"{pid}_v{j+1}"
            variants.append(ProductVariant(id=vid, label=v[1], price=v[2], unit=v[3]))
        PRODUCTS[pid] = Product(
            id=pid, name=name, brand=brand, aisle_id=aisle, description=desc,
            base_price=price, unit=unit, image_emoji=emoji, tags=tags, organic=organic,
            variants=variants, rating=round(3.5 + random.random() * 1.5, 1),
            review_count=random.randint(10, 500),
        )

    # Update aisle product counts
    for aid in AISLES:
        AISLES[aid].product_count = sum(1 for p in PRODUCTS.values() if p.aisle_id == aid)

    # Promotions
    promos = [
        ("Weekly Special: 20% Off Produce", "Save on all fresh fruits and vegetables", "percentage", 20, [], ["produce"], 0, "", True, True),
        ("Buy 2 Get 1 Free Yogurt", "Mix and match any Chobani yogurt", "bogo", 0, ["prod_008"], [], 0, "", True, True),
        ("$5 Off Orders Over $50", "Spend $50 and save $5 instantly", "fixed", 5, [], [], 50, "SAVE5", True, False),
        ("$10 Off First Order", "New customer discount on orders over $30", "fixed", 10, [], [], 30, "WELCOME10", True, True),
        ("Meat Monday: 15% Off", "All meat and seafood 15% off on Mondays", "percentage", 15, [], ["meat"], 0, "", True, False),
        ("Bakery Bundle: 3 for $12", "Any 3 bakery items for $12", "bundle", 12, [], ["bakery"], 0, "", True, False),
    ]
    for i, (title, desc, dtype, val, pids, aids, minp, code, active, popup) in enumerate(promos):
        pid = f"promo_{i+1:03d}"
        PROMOTIONS[pid] = Promotion(
            id=pid, title=title, description=desc, discount_type=dtype,
            discount_value=val, product_ids=pids, aisle_ids=aids,
            min_purchase=minp, code=code, active=active, popup=popup,
            valid_until=(date.today() + timedelta(days=7)).isoformat(),
        )

    # Test users
    for email, pw, name, phone, points in [
        ("sarah@email.com", "shop123", "Sarah Miller", "+1-555-0301", 2450),
        ("mike@email.com", "fresh456", "Mike Chen", "+1-555-0302", 890),
    ]:
        uid = f"user_{uuid.uuid4().hex[:8]}"
        card = f"FM-{random.randint(100000,999999)}"
        USERS[uid] = User(id=uid, email=email, name=name, password_hash=_hash(pw),
                          phone=phone, loyalty_card=card, loyalty_points=points)
        EMAIL_INDEX[email] = uid


# ── Auth ──

def create_token(user):
    return jwt.encode({"user_id": user.id, "email": user.email, "name": user.name,
                        "exp": datetime.utcnow() + timedelta(hours=24)},
                       JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    if not authorization:
        raise HTTPException(status_code=401, detail="Login required")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        payload = jwt.decode(parts[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = USERS.get(payload.get("user_id"))
        if not user: raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── App ──

@asynccontextmanager
async def lifespan(app):
    seed_data()
    yield

app = FastAPI(title="FreshMart", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


# ═══ PUBLIC ENDPOINTS (8) ═══

@app.get("/api/aisles")
def list_aisles():
    return {"aisles": [a.model_dump() for a in AISLES.values()], "total": len(AISLES)}

@app.get("/api/aisles/{aisle_id}")
def get_aisle(aisle_id: str):
    if aisle_id not in AISLES: raise HTTPException(404, "Aisle not found")
    aisle = AISLES[aisle_id]
    products = [p.model_dump() for p in PRODUCTS.values() if p.aisle_id == aisle_id]
    return {"aisle": aisle.model_dump(), "products": products, "total": len(products)}

@app.get("/api/products")
def search_products(
    q: Optional[str] = Query(None), aisle: Optional[str] = Query(None),
    organic: Optional[bool] = Query(None), tag: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None), max_price: Optional[float] = Query(None),
    sort_by: Optional[str] = Query("name"),
):
    items = list(PRODUCTS.values())
    if aisle: items = [i for i in items if i.aisle_id == aisle]
    if organic is not None: items = [i for i in items if i.organic == organic]
    if tag: items = [i for i in items if tag in i.tags]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i.name.lower() or ql in i.description.lower() or ql in i.brand.lower()
                 or any(ql in t for t in i.tags)]
    if min_price is not None: items = [i for i in items if i.base_price >= min_price]
    if max_price is not None: items = [i for i in items if i.base_price <= max_price]
    if sort_by == "price_asc": items.sort(key=lambda x: x.base_price)
    elif sort_by == "price_desc": items.sort(key=lambda x: x.base_price, reverse=True)
    elif sort_by == "rating": items.sort(key=lambda x: x.rating, reverse=True)
    else: items.sort(key=lambda x: x.name)
    return {"products": [i.model_dump() for i in items], "total": len(items)}

@app.get("/api/products/{product_id}")
def get_product(product_id: str):
    if product_id not in PRODUCTS: raise HTTPException(404, "Product not found")
    p = PRODUCTS[product_id]
    data = p.model_dump()
    data["aisle_name"] = AISLES.get(p.aisle_id, Aisle(id="",name="",icon="",description="")).name
    # Check if product is in any active promotion
    data["promotions"] = [promo.model_dump() for promo in PROMOTIONS.values()
                          if promo.active and (p.id in promo.product_ids or p.aisle_id in promo.aisle_ids)]
    return data

@app.get("/api/promotions")
def list_promotions(active_only: bool = Query(True), popup_only: bool = Query(False)):
    promos = list(PROMOTIONS.values())
    if active_only: promos = [p for p in promos if p.active]
    if popup_only: promos = [p for p in promos if p.popup]
    return {"promotions": [p.model_dump() for p in promos], "total": len(promos)}

@app.get("/api/promotions/{promo_id}")
def get_promotion(promo_id: str):
    if promo_id not in PROMOTIONS: raise HTTPException(404, "Promotion not found")
    promo = PROMOTIONS[promo_id]
    products = [PRODUCTS[pid].model_dump() for pid in promo.product_ids if pid in PRODUCTS]
    return {"promotion": promo.model_dump(), "applicable_products": products}

@app.get("/api/store/info")
def store_info():
    return {
        "name": "FreshMart", "tagline": "Fresh food, fair prices",
        "address": "789 Market Street, San Francisco, CA 94103",
        "phone": "+1-415-555-MART",
        "hours": {"mon-sat": "7:00-22:00", "sun": "8:00-21:00"},
        "delivery_zones": ["94102", "94103", "94104", "94105", "94107", "94108", "94110", "94111"],
        "delivery_fee": 5.99, "free_delivery_min": 75.00,
        "loyalty_program": "FreshRewards — earn 1 point per $1 spent",
    }

@app.get("/api/delivery-slots")
def delivery_slots(date: Optional[str] = Query(None)):
    target = date or (datetime.now().date() + timedelta(days=1)).isoformat()
    slots = []
    for hour in range(8, 21, 2):
        slot_id = f"{target}_{hour:02d}"
        available = random.Random(slot_id).random() > 0.3
        slots.append({"id": slot_id, "date": target, "time": f"{hour:02d}:00-{hour+2:02d}:00",
                       "available": available, "fee": 5.99 if hour < 12 else 3.99})
    return {"date": target, "slots": slots}


# ═══ AUTH ENDPOINTS (2) ═══

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
    if not uid or USERS[uid].password_hash != _hash(req.password):
        raise HTTPException(401, "Invalid credentials")
    user = USERS[uid]
    return {"token": create_token(user), "user_id": user.id, "name": user.name,
            "email": user.email, "loyalty_card": user.loyalty_card,
            "loyalty_points": user.loyalty_points, "message": f"Welcome back, {user.name}!"}

@app.post("/api/auth/register")
def register(req: RegisterReq):
    if req.email.lower() in EMAIL_INDEX: raise HTTPException(409, "Email already registered")
    if len(req.password) < 6: raise HTTPException(400, "Password too short")
    uid = f"user_{uuid.uuid4().hex[:8]}"
    card = f"FM-{random.randint(100000,999999)}"
    user = User(id=uid, email=req.email.lower(), name=req.name, password_hash=_hash(req.password),
                phone=req.phone, loyalty_card=card, loyalty_points=100)  # 100 welcome points
    USERS[uid] = user
    EMAIL_INDEX[req.email.lower()] = uid
    return {"token": create_token(user), "user_id": uid, "name": req.name, "email": req.email,
            "loyalty_card": card, "loyalty_points": 100,
            "message": f"Welcome to FreshMart, {req.name}! Your loyalty card: {card}. 100 welcome points added!"}


# ═══ PROTECTED ENDPOINTS (15) ═══

@app.get("/api/auth/profile")
def get_profile(user: User = Depends(get_current_user)):
    return {"id": user.id, "name": user.name, "email": user.email, "phone": user.phone,
            "loyalty_card": user.loyalty_card, "loyalty_points": user.loyalty_points,
            "favorites_count": len(user.favorites)}

# ── Cart ──

class AddToCartReq(BaseModel):
    product_id: str
    variant_id: Optional[str] = None
    quantity: int = 1
    notes: str = ""

class UpdateCartReq(BaseModel):
    product_id: str
    quantity: int

class RemoveCartReq(BaseModel):
    product_id: str

class CouponReq(BaseModel):
    code: str

@app.post("/api/cart")
def create_cart(user: User = Depends(get_current_user)):
    cid = f"cart_{uuid.uuid4().hex[:8]}"
    cart = Cart(id=cid, user_id=user.id, created_at=datetime.utcnow().isoformat())
    CARTS[cid] = cart
    return {"cart": {"id": cid, "items": [], "subtotal": 0, "discount": 0, "tax": 0, "total": 0}}

def _calculate_cart(cart: Cart) -> dict:
    items_detail = []
    subtotal = 0
    for ci in cart.items:
        product = PRODUCTS.get(ci.product_id)
        if not product: continue
        price = product.base_price
        variant_label = ""
        if ci.variant_id:
            for v in product.variants:
                if v.id == ci.variant_id:
                    price = v.price
                    variant_label = v.label
                    break
        line_total = round(price * ci.quantity, 2)
        subtotal += line_total
        items_detail.append({
            "product_id": ci.product_id, "name": product.name, "brand": product.brand,
            "emoji": product.image_emoji, "price": price, "variant": variant_label,
            "quantity": ci.quantity, "notes": ci.notes, "line_total": line_total,
        })

    # Apply promotions
    discount = 0
    applied_promos = []
    for promo in PROMOTIONS.values():
        if not promo.active: continue
        if promo.discount_type == "percentage" and promo.aisle_ids:
            for item in items_detail:
                p = PRODUCTS.get(item["product_id"])
                if p and p.aisle_id in promo.aisle_ids:
                    d = round(item["line_total"] * promo.discount_value / 100, 2)
                    discount += d
                    applied_promos.append({"promo": promo.title, "saved": d})

    # Apply coupon
    if cart.coupon_code:
        for promo in PROMOTIONS.values():
            if promo.code and promo.code.upper() == cart.coupon_code.upper() and promo.active:
                if subtotal >= promo.min_purchase:
                    if promo.discount_type == "fixed":
                        discount += promo.discount_value
                        applied_promos.append({"promo": promo.title, "saved": promo.discount_value})

    tax = round((subtotal - discount) * 0.0875, 2)
    total = round(subtotal - discount + tax, 2)

    return {
        "cart": {"id": cart.id, "items_detail": items_detail, "item_count": len(items_detail),
                 "subtotal": round(subtotal, 2), "discount": round(discount, 2),
                 "tax": tax, "total": max(total, 0),
                 "coupon": cart.coupon_code or None,
                 "applied_promotions": applied_promos},
    }

@app.get("/api/cart/{cart_id}")
def get_cart(cart_id: str, user: User = Depends(get_current_user)):
    if cart_id not in CARTS: raise HTTPException(404, "Cart not found")
    return _calculate_cart(CARTS[cart_id])

@app.post("/api/cart/{cart_id}/add")
def add_to_cart(cart_id: str, req: AddToCartReq, user: User = Depends(get_current_user)):
    if cart_id not in CARTS: raise HTTPException(404, "Cart not found")
    if req.product_id not in PRODUCTS: raise HTTPException(404, "Product not found")
    cart = CARTS[cart_id]
    for item in cart.items:
        if item.product_id == req.product_id and item.variant_id == req.variant_id:
            item.quantity += req.quantity
            return _calculate_cart(cart)
    cart.items.append(CartItem(product_id=req.product_id, variant_id=req.variant_id,
                               quantity=req.quantity, notes=req.notes))
    return _calculate_cart(cart)

@app.post("/api/cart/{cart_id}/update")
def update_cart(cart_id: str, req: UpdateCartReq, user: User = Depends(get_current_user)):
    if cart_id not in CARTS: raise HTTPException(404, "Cart not found")
    cart = CARTS[cart_id]
    if req.quantity <= 0:
        cart.items = [i for i in cart.items if i.product_id != req.product_id]
    else:
        for item in cart.items:
            if item.product_id == req.product_id:
                item.quantity = req.quantity
                break
    return _calculate_cart(cart)

@app.post("/api/cart/{cart_id}/remove")
def remove_from_cart(cart_id: str, req: RemoveCartReq, user: User = Depends(get_current_user)):
    if cart_id not in CARTS: raise HTTPException(404, "Cart not found")
    cart = CARTS[cart_id]
    cart.items = [i for i in cart.items if i.product_id != req.product_id]
    return _calculate_cart(cart)

@app.post("/api/cart/{cart_id}/coupon")
def apply_coupon(cart_id: str, req: CouponReq, user: User = Depends(get_current_user)):
    if cart_id not in CARTS: raise HTTPException(404, "Cart not found")
    valid = any(p.code and p.code.upper() == req.code.upper() and p.active for p in PROMOTIONS.values())
    if not valid: raise HTTPException(400, f"Invalid coupon code: {req.code}")
    CARTS[cart_id].coupon_code = req.code.upper()
    return _calculate_cart(CARTS[cart_id])

@app.delete("/api/cart/{cart_id}/coupon")
def remove_coupon(cart_id: str, user: User = Depends(get_current_user)):
    if cart_id not in CARTS: raise HTTPException(404, "Cart not found")
    CARTS[cart_id].coupon_code = ""
    return _calculate_cart(CARTS[cart_id])

# ── Checkout ──

class CheckoutReq(BaseModel):
    cart_id: str
    order_type: str = "pickup"
    delivery_address: str = ""
    delivery_slot: str = ""

@app.post("/api/checkout")
def checkout(req: CheckoutReq, user: User = Depends(get_current_user)):
    if req.cart_id not in CARTS: raise HTTPException(404, "Cart not found")
    cart = CARTS[req.cart_id]
    if not cart.items: raise HTTPException(400, "Cart is empty")
    if req.order_type == "delivery" and not req.delivery_address:
        raise HTTPException(400, "Delivery address required")

    calc = _calculate_cart(cart)["cart"]
    points_earned = int(calc["total"])  # 1 point per $1

    oid = f"ord_{uuid.uuid4().hex[:8]}"
    order = Order(
        id=oid, user_id=user.id, items=calc["items_detail"],
        subtotal=calc["subtotal"], discount=calc["discount"],
        tax=calc["tax"], total=calc["total"],
        loyalty_points_earned=points_earned,
        order_type=req.order_type, delivery_address=req.delivery_address,
        delivery_slot=req.delivery_slot, created_at=datetime.utcnow().isoformat(),
    )
    ORDERS[oid] = order
    user.loyalty_points += points_earned
    LOYALTY_HISTORY.append(LoyaltyTransaction(
        id=f"lt_{uuid.uuid4().hex[:8]}", user_id=user.id, points=points_earned,
        type="earned", description=f"Order {oid}", created_at=datetime.utcnow().isoformat(),
    ))
    del CARTS[req.cart_id]
    return {"order": order.model_dump(),
            "message": f"Order {oid} confirmed! Total: ${calc['total']}. "
                       f"You earned {points_earned} loyalty points!"}

# ── Orders ──

@app.get("/api/orders")
def list_orders(user: User = Depends(get_current_user)):
    user_orders = [o.model_dump() for o in ORDERS.values() if o.user_id == user.id]
    return {"orders": user_orders, "total": len(user_orders)}

@app.get("/api/orders/{order_id}")
def get_order(order_id: str, user: User = Depends(get_current_user)):
    if order_id not in ORDERS: raise HTTPException(404, "Order not found")
    return {"order": ORDERS[order_id].model_dump()}

# ── Loyalty ──

@app.get("/api/loyalty")
def loyalty_balance(user: User = Depends(get_current_user)):
    return {"loyalty_card": user.loyalty_card, "points": user.loyalty_points,
            "dollar_value": round(user.loyalty_points * 0.01, 2),
            "message": f"You have {user.loyalty_points} points (${round(user.loyalty_points*0.01,2)} value)"}

@app.get("/api/loyalty/history")
def loyalty_history(user: User = Depends(get_current_user)):
    txns = [t.model_dump() for t in LOYALTY_HISTORY if t.user_id == user.id]
    return {"transactions": txns, "total": len(txns)}

class RedeemReq(BaseModel):
    points: int

@app.post("/api/loyalty/redeem")
def redeem_points(req: RedeemReq, user: User = Depends(get_current_user)):
    if req.points > user.loyalty_points:
        raise HTTPException(400, f"Not enough points. You have {user.loyalty_points}")
    if req.points < 100:
        raise HTTPException(400, "Minimum 100 points to redeem")
    discount = round(req.points * 0.01, 2)
    user.loyalty_points -= req.points
    LOYALTY_HISTORY.append(LoyaltyTransaction(
        id=f"lt_{uuid.uuid4().hex[:8]}", user_id=user.id, points=-req.points,
        type="redeemed", description=f"Redeemed for ${discount} discount",
        created_at=datetime.utcnow().isoformat(),
    ))
    return {"redeemed": req.points, "discount": discount, "remaining_points": user.loyalty_points,
            "message": f"Redeemed {req.points} points for ${discount} off your next order!"}

# ── Favorites ──

@app.get("/api/favorites")
def list_favorites(user: User = Depends(get_current_user)):
    favs = [PRODUCTS[pid].model_dump() for pid in user.favorites if pid in PRODUCTS]
    return {"favorites": favs, "total": len(favs)}

# ── SPA ──

@app.get("/", response_class=HTMLResponse)
def serve_spa():
    spa_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if spa_path.exists():
        return HTMLResponse(content=spa_path.read_text())
    return HTMLResponse(content="<h1>🛒 FreshMart</h1><p>SPA at /frontend/index.html</p>")
