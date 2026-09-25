"""
Subway Shopping Simulation - Data Models & In-Memory Store
"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
import uuid
from datetime import datetime


# ── Enums ──

class Category(str, Enum):
    ELECTRONICS = "electronics"
    CLOTHING = "clothing"
    BOOKS = "books"
    HOME = "home"
    SPORTS = "sports"


class StockStatus(str, Enum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"


# ── Models ──

class Product(BaseModel):
    id: str
    name: str
    description: str
    price: float
    category: Category
    rating: float = Field(ge=0, le=5)
    review_count: int = 0
    stock_status: StockStatus = StockStatus.IN_STOCK
    stock_quantity: int = 0
    image_url: str = ""


class CartItem(BaseModel):
    product_id: str
    quantity: int = Field(ge=1, le=10)


class Cart(BaseModel):
    id: str
    items: list[CartItem] = []
    created_at: str = ""


class ShippingInfo(BaseModel):
    name: str
    address: str
    city: str
    zip_code: str
    country: str = "US"


class PaymentInfo(BaseModel):
    card_last_four: str = Field(min_length=4, max_length=4)
    card_type: str = "visa"


class Order(BaseModel):
    id: str
    cart_id: str
    items: list[CartItem] = []
    total: float = 0.0
    shipping: Optional[ShippingInfo] = None
    payment: Optional[PaymentInfo] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: str = ""


# ── Request/Response Schemas ──

class SearchQuery(BaseModel):
    q: Optional[str] = None
    category: Optional[Category] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    sort_by: Optional[str] = "relevance"  # relevance, price_asc, price_desc, rating


class AddToCartRequest(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1, le=10)


class CheckoutRequest(BaseModel):
    cart_id: str
    shipping: ShippingInfo
    payment: PaymentInfo


class ProductListResponse(BaseModel):
    products: list[Product]
    total: int
    page: int = 1
    per_page: int = 20


class CartResponse(BaseModel):
    cart: Cart
    items_detail: list[dict] = []
    subtotal: float = 0.0
    tax: float = 0.0
    total: float = 0.0


class OrderResponse(BaseModel):
    order: Order
    message: str = ""


# ── In-Memory Database ──

PRODUCTS: dict[str, Product] = {}
CARTS: dict[str, Cart] = {}
ORDERS: dict[str, Order] = {}


def seed_products():
    """Populate the store with sample products."""
    catalog = [
        ("Wireless Headphones XR-500", "Premium noise-cancelling wireless headphones with 40h battery life.", 79.99, Category.ELECTRONICS, 4.3, 2841, 45),
        ("Ultra Slim Laptop Stand", "Ergonomic aluminum laptop stand, adjustable height.", 34.99, Category.ELECTRONICS, 4.6, 1203, 120),
        ("Smart Watch Pro", "Fitness tracker with heart rate, GPS, and 7-day battery.", 199.99, Category.ELECTRONICS, 4.1, 3452, 30),
        ("USB-C Hub 7-in-1", "Multi-port adapter: HDMI, USB-A, SD card, ethernet.", 29.99, Category.ELECTRONICS, 4.4, 892, 200),
        ("Mechanical Keyboard RGB", "Cherry MX switches, per-key RGB, aluminum frame.", 89.99, Category.ELECTRONICS, 4.7, 1567, 60),
        ("Cotton Crew T-Shirt", "100% organic cotton, relaxed fit, multiple colors.", 24.99, Category.CLOTHING, 4.2, 4521, 300),
        ("Running Shoes Aero", "Lightweight mesh upper, responsive cushioning.", 119.99, Category.CLOTHING, 4.5, 2103, 80),
        ("Wool Blend Sweater", "Merino wool blend, crew neck, machine washable.", 59.99, Category.CLOTHING, 4.0, 756, 50),
        ("Denim Jacket Classic", "Medium wash, button front, chest pockets.", 69.99, Category.CLOTHING, 4.3, 1890, 40),
        ("The Art of Systems Thinking", "A practical guide to understanding complex systems.", 18.99, Category.BOOKS, 4.6, 932, 150),
        ("Deep Learning Fundamentals", "Comprehensive introduction to neural networks and AI.", 45.99, Category.BOOKS, 4.8, 2341, 90),
        ("Science Fiction Anthology 2025", "Collection of award-winning short stories.", 14.99, Category.BOOKS, 4.1, 567, 200),
        ("Stainless Steel Water Bottle", "Double-wall insulated, 32oz, keeps cold 24h.", 22.99, Category.HOME, 4.5, 3201, 250),
        ("Ceramic Plant Pot Set", "Set of 3, drainage holes, minimalist design.", 31.99, Category.HOME, 4.3, 1102, 70),
        ("LED Desk Lamp", "Adjustable brightness, USB charging port, touch control.", 39.99, Category.HOME, 4.4, 1845, 100),
        ("Yoga Mat Premium", "Non-slip, 6mm thick, carrying strap included.", 29.99, Category.SPORTS, 4.6, 2678, 140),
        ("Resistance Bands Set", "5 levels, latex-free, with door anchor and bag.", 19.99, Category.SPORTS, 4.2, 1432, 300),
        ("Jump Rope Speed", "Ball bearing handles, adjustable length, lightweight.", 12.99, Category.SPORTS, 4.4, 876, 400),
    ]

    for i, (name, desc, price, cat, rating, reviews, stock) in enumerate(catalog):
        pid = f"prod_{i+1:03d}"
        status = StockStatus.IN_STOCK if stock > 20 else (StockStatus.LOW_STOCK if stock > 0 else StockStatus.OUT_OF_STOCK)
        PRODUCTS[pid] = Product(
            id=pid, name=name, description=desc, price=price,
            category=cat, rating=rating, review_count=reviews,
            stock_status=status, stock_quantity=stock,
            image_url=f"/static/products/{pid}.jpg"
        )


def create_cart() -> Cart:
    cart_id = f"cart_{uuid.uuid4().hex[:8]}"
    cart = Cart(id=cart_id, created_at=datetime.utcnow().isoformat())
    CARTS[cart_id] = cart
    return cart


def create_order(cart_id: str, shipping: ShippingInfo, payment: PaymentInfo) -> Order:
    order_id = f"order_{uuid.uuid4().hex[:8]}"
    cart = CARTS[cart_id]

    total = 0.0
    for item in cart.items:
        product = PRODUCTS[item.product_id]
        total += product.price * item.quantity

    tax = round(total * 0.08, 2)

    order = Order(
        id=order_id, cart_id=cart_id, items=cart.items,
        total=round(total + tax, 2), shipping=shipping,
        payment=payment, status=OrderStatus.CONFIRMED,
        created_at=datetime.utcnow().isoformat()
    )
    ORDERS[order_id] = order
    return order
