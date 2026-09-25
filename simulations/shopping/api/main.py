"""
Subway Shopping Simulation - FastAPI Application (Level 2: Auth & Sessions)

Public endpoints (no auth required):
  GET  /api/products          - Search/list products
  GET  /api/products/{id}     - Get product detail
  POST /api/auth/register     - Create account
  POST /api/auth/login        - Login, get JWT token

Protected endpoints (require Authorization: Bearer <token>):
  GET  /api/auth/profile      - Get user profile
  POST /api/cart              - Create new cart (auto-linked to user)
  GET  /api/cart/{id}         - Get cart contents
  POST /api/cart/{id}/add     - Add item to cart
  POST /api/cart/{id}/update  - Update item quantity
  POST /api/cart/{id}/remove  - Remove item from cart
  POST /api/checkout          - Place order
  GET  /api/orders/{id}       - Get order status
  GET  /api/orders            - Get user's order history
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from typing import Optional
from pathlib import Path

from models import (
    PRODUCTS, CARTS, ORDERS, seed_products, create_cart, create_order,
    Product, Category, StockStatus,
    AddToCartRequest, CheckoutRequest,
    ProductListResponse, CartResponse, OrderResponse
)
from auth import (
    USERS, seed_users, register_user, authenticate_user,
    get_user_from_token, create_token, get_user_by_id,
    RegisterRequest, LoginRequest, AuthResponse, UserProfile,
    User,
)


@asynccontextmanager
async def lifespan(app):
    seed_products()
    seed_users()
    yield


app = FastAPI(
    title="Subway Shopping Simulation",
    description="Simulated e-commerce site with authentication (Level 2)",
    version="0.2.0",
    lifespan=lifespan,
)

# Serve static files - check both possible directory structures
static_dir = Path(__file__).parent / "static"
if not static_dir.exists():
    static_dir = Path(__file__).parent.parent / "frontend" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── Auth Dependency ──

def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    """Extract and validate user from Authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required. Use: Authorization: Bearer <token>")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format. Use: Bearer <token>")

    user = get_user_from_token(parts[1])
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token. Please login again.")

    return user


def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[User]:
    """Extract user if token provided, None otherwise."""
    if not authorization:
        return None
    try:
        return get_current_user(authorization)
    except HTTPException:
        return None


# ── Auth Endpoints ──

@app.post("/api/auth/register", response_model=AuthResponse)
def register(req: RegisterRequest):
    """Create a new account."""
    if not req.email or not req.password or not req.name:
        raise HTTPException(status_code=400, detail="Email, password, and name are required")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    try:
        user = register_user(req.email, req.password, req.name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    token = create_token(user)
    return AuthResponse(
        token=token, user_id=user.id, name=user.name, email=user.email,
        message=f"Account created for {user.name}. Use the token for authenticated requests."
    )


@app.post("/api/auth/login", response_model=AuthResponse)
def login(req: LoginRequest):
    """Login and get a JWT token."""
    user = authenticate_user(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token(user)
    return AuthResponse(
        token=token, user_id=user.id, name=user.name, email=user.email,
        message=f"Welcome back, {user.name}!"
    )


@app.get("/api/auth/profile", response_model=UserProfile)
def get_profile(user: User = Depends(get_current_user)):
    """Get the current user's profile."""
    order_count = sum(1 for o in ORDERS.values() if o.cart_id and
                      CARTS.get(o.cart_id) and
                      hasattr(CARTS.get(o.cart_id), '_user_id') and
                      getattr(CARTS.get(o.cart_id), '_user_id', None) == user.id)
    return UserProfile(
        id=user.id, email=user.email, name=user.name,
        cart_id=user.cart_id, order_count=order_count,
        created_at=user.created_at,
    )


# ── Product Endpoints ──

@app.get("/api/products", response_model=ProductListResponse)
def search_products(
    q: Optional[str] = Query(None, description="Search query"),
    category: Optional[Category] = Query(None, description="Filter by category"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price"),
    max_price: Optional[float] = Query(None, description="Maximum price"),
    sort_by: Optional[str] = Query("relevance", description="Sort: relevance, price_asc, price_desc, rating"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
):
    """Search and filter products."""
    results = list(PRODUCTS.values())

    # Filter by category FIRST (before text search, so q doesn't eliminate category matches)
    if category:
        results = [p for p in results if p.category == category]

    # Filter by search query — match against name, description, AND category
    if q:
        q_lower = q.lower().strip()
        if q_lower:  # Skip empty strings
            results = [p for p in results if (
                q_lower in p.name.lower()
                or q_lower in p.description.lower()
                or q_lower in p.category.value.lower()
                # Also match individual words for multi-word queries
                or any(word in p.name.lower() or word in p.description.lower()
                       for word in q_lower.split() if len(word) > 2)
            )]

    # Fallback: if q + category returned nothing, retry q-only across all products
    # This handles cases where the agent guessed the wrong category
    if not results and q and category:
        q_lower = q.lower().strip()
        if q_lower:
            all_products = list(PRODUCTS.values())
            results = [p for p in all_products if (
                q_lower in p.name.lower()
                or q_lower in p.description.lower()
                or q_lower in p.category.value.lower()
                or any(word in p.name.lower() or word in p.description.lower()
                       for word in q_lower.split() if len(word) > 2)
            )]

    # Filter by price range (handle string values from agents)
    if min_price is not None:
        try:
            min_val = float(min_price)
            results = [p for p in results if p.price >= min_val]
        except (ValueError, TypeError):
            pass
    if max_price is not None:
        try:
            max_val = float(max_price)
            results = [p for p in results if p.price <= max_val]
        except (ValueError, TypeError):
            pass

    # Sort
    if sort_by == "price_asc":
        results.sort(key=lambda p: p.price)
    elif sort_by == "price_desc":
        results.sort(key=lambda p: p.price, reverse=True)
    elif sort_by == "rating":
        results.sort(key=lambda p: p.rating, reverse=True)

    total = len(results)
    start = (page - 1) * per_page
    end = start + per_page
    results = results[start:end]

    return ProductListResponse(products=results, total=total, page=page, per_page=per_page)


@app.get("/api/products/{product_id}", response_model=Product)
def get_product(product_id: str):
    """Get a single product by ID."""
    if product_id not in PRODUCTS:
        raise HTTPException(status_code=404, detail="Product not found")
    return PRODUCTS[product_id]


# ── Cart Endpoints (Protected — require login) ──

@app.post("/api/cart", response_model=CartResponse)
def new_cart(user: User = Depends(get_current_user)):
    """Create a new shopping cart linked to the logged-in user."""
    cart = create_cart()
    # Link cart to user
    user.cart_id = cart.id
    return CartResponse(cart=cart, subtotal=0, tax=0, total=0)


@app.get("/api/cart/{cart_id}", response_model=CartResponse)
def get_cart(cart_id: str):
    """Get cart contents with item details and totals."""
    if cart_id not in CARTS:
        raise HTTPException(status_code=404, detail="Cart not found")

    cart = CARTS[cart_id]
    items_detail = []
    subtotal = 0.0

    for item in cart.items:
        product = PRODUCTS.get(item.product_id)
        if product:
            line_total = product.price * item.quantity
            subtotal += line_total
            items_detail.append({
                "product_id": item.product_id,
                "name": product.name,
                "price": product.price,
                "quantity": item.quantity,
                "line_total": round(line_total, 2),
                "stock_status": product.stock_status.value
            })

    tax = round(subtotal * 0.08, 2)
    return CartResponse(
        cart=cart, items_detail=items_detail,
        subtotal=round(subtotal, 2), tax=tax,
        total=round(subtotal + tax, 2)
    )


@app.post("/api/cart/{cart_id}/add", response_model=CartResponse)
def add_to_cart(cart_id: str, req: AddToCartRequest, user: User = Depends(get_current_user)):
    """Add a product to the cart. Requires login."""
    if cart_id not in CARTS:
        raise HTTPException(status_code=404, detail="Cart not found")
    if req.product_id not in PRODUCTS:
        raise HTTPException(status_code=404, detail="Product not found")

    product = PRODUCTS[req.product_id]
    if product.stock_status == StockStatus.OUT_OF_STOCK:
        raise HTTPException(status_code=400, detail="Product is out of stock")

    cart = CARTS[cart_id]

    # Check if product already in cart
    for item in cart.items:
        if item.product_id == req.product_id:
            new_qty = item.quantity + req.quantity
            if new_qty > 10:
                raise HTTPException(status_code=400, detail="Maximum 10 items per product")
            item.quantity = new_qty
            return get_cart(cart_id)

    # Add new item
    cart.items.append(CartItem(product_id=req.product_id, quantity=req.quantity))
    return get_cart(cart_id)


from pydantic import BaseModel

class UpdateCartRequest(BaseModel):
    product_id: str
    quantity: int

class RemoveCartRequest(BaseModel):
    product_id: str


@app.post("/api/cart/{cart_id}/update", response_model=CartResponse)
def update_cart_item(cart_id: str, req: UpdateCartRequest, user: User = Depends(get_current_user)):
    """Update quantity of an item in the cart. Requires login."""
    if cart_id not in CARTS:
        raise HTTPException(status_code=404, detail="Cart not found")

    cart = CARTS[cart_id]
    for item in cart.items:
        if item.product_id == req.product_id:
            if req.quantity <= 0:
                cart.items.remove(item)
            elif req.quantity > 10:
                raise HTTPException(status_code=400, detail="Maximum 10 items per product")
            else:
                item.quantity = req.quantity
            return get_cart(cart_id)

    raise HTTPException(status_code=404, detail="Item not in cart")


@app.post("/api/cart/{cart_id}/remove", response_model=CartResponse)
def remove_from_cart(cart_id: str, req: RemoveCartRequest, user: User = Depends(get_current_user)):
    """Remove a product from the cart. Requires login."""
    if cart_id not in CARTS:
        raise HTTPException(status_code=404, detail="Cart not found")

    cart = CARTS[cart_id]
    cart.items = [i for i in cart.items if i.product_id != req.product_id]
    return get_cart(cart_id)


# ── Checkout Endpoint (Protected) ──

@app.post("/api/checkout", response_model=OrderResponse)
def checkout(req: CheckoutRequest, user: User = Depends(get_current_user)):
    """Place an order from a cart. Requires login."""
    if req.cart_id not in CARTS:
        raise HTTPException(status_code=404, detail="Cart not found")

    cart = CARTS[req.cart_id]
    if not cart.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # Validate stock
    for item in cart.items:
        product = PRODUCTS.get(item.product_id)
        if not product:
            raise HTTPException(status_code=400, detail=f"Product {item.product_id} not found")
        if product.stock_status == StockStatus.OUT_OF_STOCK:
            raise HTTPException(status_code=400, detail=f"{product.name} is out of stock")
        if product.stock_quantity < item.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {product.name}")

    # Deduct stock
    for item in cart.items:
        product = PRODUCTS[item.product_id]
        product.stock_quantity -= item.quantity
        if product.stock_quantity == 0:
            product.stock_status = StockStatus.OUT_OF_STOCK
        elif product.stock_quantity <= 20:
            product.stock_status = StockStatus.LOW_STOCK

    order = create_order(req.cart_id, req.shipping, req.payment)

    return OrderResponse(order=order, message=f"Order {order.id} confirmed! Total: ${order.total}")


# ── Order Endpoints (Protected) ──

@app.get("/api/orders", response_model=dict)
def get_user_orders(user: User = Depends(get_current_user)):
    """Get the logged-in user's order history."""
    user_orders = []
    for order in ORDERS.values():
        # Match orders by cart ownership
        if order.cart_id and CARTS.get(order.cart_id):
            if user.cart_id == order.cart_id or getattr(CARTS.get(order.cart_id), '_user_id', None) == user.id:
                user_orders.append(order)
    return {"orders": [o.model_dump() for o in user_orders], "total": len(user_orders)}


@app.get("/api/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str, user: User = Depends(get_current_user)):
    """Check order status. Requires login."""
    if order_id not in ORDERS:
        raise HTTPException(status_code=404, detail="Order not found")
    order = ORDERS[order_id]
    return OrderResponse(order=order, message=f"Order status: {order.status.value}")


# ── HTML Frontends ──

@app.get("/spa", response_class=HTMLResponse)
def spa_frontend():
    """Serve the React SPA frontend (Level 3 — dynamic frontend)."""
    spa_path = Path(__file__).parent.parent / "frontend" / "spa.html"
    if spa_path.exists():
        return HTMLResponse(content=spa_path.read_text())
    return HTMLResponse(content="<h1>SPA not found</h1>", status_code=404)


@app.get("/", response_class=HTMLResponse)
def homepage():
    """Serve the server-rendered shopping frontend."""
    return get_frontend_html()


from models import CartItem

def get_frontend_html():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SubwayShop - Demo Store</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }
  
  header { background: #1a1a2e; color: white; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
  header h1 { font-size: 22px; font-weight: 600; }
  header h1 span { color: #6c63ff; }
  .cart-btn { background: #6c63ff; color: white; border: none; padding: 8px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; }
  .cart-btn:hover { background: #5a52d5; }
  
  .container { max-width: 1100px; margin: 0 auto; padding: 24px; }
  
  /* Search & Filters */
  .search-bar { display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
  .search-bar input { flex: 1; min-width: 200px; padding: 10px 16px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; }
  .search-bar select, .search-bar button { padding: 10px 16px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; background: white; cursor: pointer; }
  .search-bar button { background: #6c63ff; color: white; border: none; }
  
  /* Product Grid */
  .products { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 20px; }
  .product-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); transition: transform 0.15s; cursor: pointer; }
  .product-card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.1); }
  .product-card h3 { font-size: 16px; margin-bottom: 6px; }
  .product-card .price { font-size: 20px; font-weight: 700; color: #1a1a2e; margin: 8px 0; }
  .product-card .meta { font-size: 13px; color: #777; margin-bottom: 4px; }
  .product-card .rating { color: #f4a940; }
  .stock-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
  .stock-in { background: #e8f5e9; color: #2e7d32; }
  .stock-low { background: #fff3e0; color: #e65100; }
  .stock-out { background: #ffebee; color: #c62828; }
  .add-btn { width: 100%; margin-top: 12px; padding: 10px; background: #6c63ff; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 500; }
  .add-btn:hover { background: #5a52d5; }
  .add-btn:disabled { background: #ccc; cursor: not-allowed; }
  
  /* Modal (Cart / Checkout / Product Detail) */
  .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 100; justify-content: center; align-items: center; }
  .modal-overlay.active { display: flex; }
  .modal { background: white; border-radius: 16px; padding: 28px; max-width: 560px; width: 90%; max-height: 80vh; overflow-y: auto; }
  .modal h2 { margin-bottom: 16px; font-size: 20px; }
  .modal-close { float: right; background: none; border: none; font-size: 24px; cursor: pointer; color: #999; }
  
  /* Cart Items */
  .cart-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #eee; }
  .cart-item .name { font-weight: 500; }
  .cart-item .qty-controls { display: flex; align-items: center; gap: 8px; }
  .cart-item .qty-controls button { width: 28px; height: 28px; border: 1px solid #ddd; border-radius: 6px; background: white; cursor: pointer; font-size: 16px; }
  .cart-total { padding: 16px 0; font-size: 18px; font-weight: 700; text-align: right; }
  
  /* Checkout Form */
  .checkout-form label { display: block; margin: 10px 0 4px; font-size: 13px; font-weight: 500; color: #555; }
  .checkout-form input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; }
  .checkout-btn { width: 100%; margin-top: 20px; padding: 14px; background: #2e7d32; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: 600; }
  .checkout-btn:hover { background: #1b5e20; }
  
  /* Confirmation */
  .confirmation { text-align: center; padding: 20px; }
  .confirmation h2 { color: #2e7d32; margin-bottom: 12px; }
  
  .empty { text-align: center; color: #999; padding: 40px; }
</style>
</head>
<body>

<header>
  <h1><span>Subway</span>Shop</h1>
  <button class="cart-btn" onclick="openCart()">Cart (<span id="cart-count">0</span>)</button>
</header>

<div class="container">
  <div class="search-bar">
    <input type="text" id="search-input" placeholder="Search products..." onkeydown="if(event.key==='Enter')searchProducts()">
    <select id="category-filter">
      <option value="">All Categories</option>
      <option value="electronics">Electronics</option>
      <option value="clothing">Clothing</option>
      <option value="books">Books</option>
      <option value="home">Home</option>
      <option value="sports">Sports</option>
    </select>
    <select id="sort-filter">
      <option value="relevance">Sort: Relevance</option>
      <option value="price_asc">Price: Low to High</option>
      <option value="price_desc">Price: High to Low</option>
      <option value="rating">Top Rated</option>
    </select>
    <button onclick="searchProducts()">Search</button>
  </div>
  
  <div class="products" id="product-grid"></div>
</div>

<!-- Cart Modal -->
<div class="modal-overlay" id="cart-modal">
  <div class="modal">
    <button class="modal-close" onclick="closeModal('cart-modal')">&times;</button>
    <h2>Shopping Cart</h2>
    <div id="cart-items"></div>
    <div class="cart-total" id="cart-total"></div>
    <button class="checkout-btn" id="checkout-start-btn" onclick="showCheckoutForm()" style="display:none">Proceed to Checkout</button>
  </div>
</div>

<!-- Checkout Modal -->
<div class="modal-overlay" id="checkout-modal">
  <div class="modal">
    <button class="modal-close" onclick="closeModal('checkout-modal')">&times;</button>
    <h2>Checkout</h2>
    <div class="checkout-form">
      <label>Full Name</label><input id="ship-name" placeholder="Jane Doe">
      <label>Address</label><input id="ship-address" placeholder="123 Main St">
      <label>City</label><input id="ship-city" placeholder="San Francisco">
      <label>ZIP Code</label><input id="ship-zip" placeholder="94102">
      <label>Card Number (last 4)</label><input id="pay-card" placeholder="4242" maxlength="4">
      <button class="checkout-btn" onclick="placeOrder()">Place Order</button>
    </div>
  </div>
</div>

<!-- Confirmation Modal -->
<div class="modal-overlay" id="confirm-modal">
  <div class="modal">
    <div class="confirmation">
      <h2 id="confirm-title">Order Confirmed!</h2>
      <p id="confirm-msg"></p>
      <button class="add-btn" style="margin-top:20px;max-width:200px" onclick="location.reload()">Continue Shopping</button>
    </div>
  </div>
</div>

<script>
let cartId = null;
let cartCount = 0;

// ── Init ──
async function init() {
  await searchProducts();
  const res = await fetch('/api/cart', { method: 'POST' });
  const data = await res.json();
  cartId = data.cart.id;
}

// ── Search Products ──
async function searchProducts() {
  const q = document.getElementById('search-input').value;
  const cat = document.getElementById('category-filter').value;
  const sort = document.getElementById('sort-filter').value;
  
  let url = `/api/products?sort_by=${sort}`;
  if (q) url += `&q=${encodeURIComponent(q)}`;
  if (cat) url += `&category=${cat}`;
  
  const res = await fetch(url);
  const data = await res.json();
  renderProducts(data.products);
}

function renderProducts(products) {
  const grid = document.getElementById('product-grid');
  if (!products.length) { grid.innerHTML = '<div class="empty">No products found</div>'; return; }
  
  grid.innerHTML = products.map(p => {
    const stockClass = p.stock_status === 'in_stock' ? 'stock-in' : p.stock_status === 'low_stock' ? 'stock-low' : 'stock-out';
    const stockLabel = p.stock_status === 'in_stock' ? 'In Stock' : p.stock_status === 'low_stock' ? 'Low Stock' : 'Out of Stock';
    const stars = '★'.repeat(Math.round(p.rating)) + '☆'.repeat(5 - Math.round(p.rating));
    return `<div class="product-card">
      <h3>${p.name}</h3>
      <div class="meta">${p.category}</div>
      <div class="price">$${p.price.toFixed(2)}</div>
      <div class="meta"><span class="rating">${stars}</span> ${p.rating} (${p.review_count} reviews)</div>
      <span class="stock-tag ${stockClass}">${stockLabel}</span>
      <p class="meta" style="margin-top:8px">${p.description}</p>
      <button class="add-btn" onclick="addToCart('${p.id}')" ${p.stock_status === 'out_of_stock' ? 'disabled' : ''}>
        ${p.stock_status === 'out_of_stock' ? 'Out of Stock' : 'Add to Cart'}
      </button>
    </div>`;
  }).join('');
}

// ── Cart ──
async function addToCart(productId) {
  if (!cartId) return;
  await fetch(`/api/cart/${cartId}/add`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_id: productId, quantity: 1 })
  });
  cartCount++;
  document.getElementById('cart-count').textContent = cartCount;
}

async function openCart() {
  if (!cartId) return;
  const res = await fetch(`/api/cart/${cartId}`);
  const data = await res.json();
  renderCart(data);
  document.getElementById('cart-modal').classList.add('active');
}

function renderCart(data) {
  const container = document.getElementById('cart-items');
  if (!data.items_detail.length) {
    container.innerHTML = '<div class="empty">Cart is empty</div>';
    document.getElementById('cart-total').innerHTML = '';
    document.getElementById('checkout-start-btn').style.display = 'none';
    return;
  }
  
  container.innerHTML = data.items_detail.map(i => `
    <div class="cart-item">
      <div>
        <div class="name">${i.name}</div>
        <div class="meta">$${i.price.toFixed(2)} each</div>
      </div>
      <div class="qty-controls">
        <button onclick="updateQty('${i.product_id}', ${i.quantity - 1})">-</button>
        <span>${i.quantity}</span>
        <button onclick="updateQty('${i.product_id}', ${i.quantity + 1})">+</button>
        <button onclick="removeItem('${i.product_id}')" style="color:#c62828;border-color:#c62828">×</button>
      </div>
      <div style="font-weight:600">$${i.line_total.toFixed(2)}</div>
    </div>
  `).join('');
  
  document.getElementById('cart-total').innerHTML = `
    Subtotal: $${data.subtotal.toFixed(2)}<br>
    <span style="font-size:14px;color:#777">Tax: $${data.tax.toFixed(2)}</span><br>
    Total: $${data.total.toFixed(2)}
  `;
  document.getElementById('checkout-start-btn').style.display = 'block';
}

async function updateQty(productId, qty) {
  if (qty <= 0) { removeItem(productId); return; }
  await fetch(`/api/cart/${cartId}/update`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_id: productId, quantity: qty })
  });
  openCart();
}

async function removeItem(productId) {
  await fetch(`/api/cart/${cartId}/remove`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_id: productId })
  });
  cartCount = Math.max(0, cartCount - 1);
  document.getElementById('cart-count').textContent = cartCount;
  openCart();
}

// ── Checkout ──
function showCheckoutForm() {
  closeModal('cart-modal');
  document.getElementById('checkout-modal').classList.add('active');
}

async function placeOrder() {
  const shipping = {
    name: document.getElementById('ship-name').value,
    address: document.getElementById('ship-address').value,
    city: document.getElementById('ship-city').value,
    zip_code: document.getElementById('ship-zip').value,
    country: 'US'
  };
  const payment = {
    card_last_four: document.getElementById('pay-card').value,
    card_type: 'visa'
  };
  
  if (!shipping.name || !shipping.address || !shipping.city || !shipping.zip_code || !payment.card_last_four) {
    alert('Please fill in all fields'); return;
  }
  
  const res = await fetch('/api/checkout', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cart_id: cartId, shipping, payment })
  });
  
  if (!res.ok) { const err = await res.json(); alert(err.detail); return; }
  
  const data = await res.json();
  closeModal('checkout-modal');
  document.getElementById('confirm-title').textContent = 'Order Confirmed!';
  document.getElementById('confirm-msg').textContent = data.message;
  document.getElementById('confirm-modal').classList.add('active');
}

function closeModal(id) { document.getElementById(id).classList.remove('active'); }

init();
</script>
</body>
</html>"""
