"""
Medusa E-Commerce Store API — Route Replica
Source: https://github.com/medusajs/medusa
Stack: Node.js/Express, file-based routing
Pattern: /store/ prefix, JWT auth, full e-commerce
Endpoints: 52 methods (customer-facing store API only)
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Header, Query
from typing import Optional
import uuid, random
from datetime import datetime, timedelta
import hashlib, jwt

JWT_SECRET = "medusa-store-secret"

PRODUCTS = {}; COLLECTIONS = {}; CATEGORIES = {}; CARTS = {}; ORDERS = {}
CUSTOMERS = {}; EMAIL_INDEX = {}; REGIONS = {}; CURRENCIES = {}

def _hash(pw): return hashlib.sha256(f"md-{pw}".encode()).hexdigest()
def _token(c): return jwt.encode({"sub":c["id"],"exp":datetime.utcnow()+timedelta(hours=24)},JWT_SECRET)
def _auth(authorization:Optional[str]=Header(None)):
    if not authorization: raise HTTPException(401)
    try:
        p=jwt.decode(authorization.replace("Bearer ",""),JWT_SECRET,algorithms=["HS256"])
        return CUSTOMERS.get(p["sub"])
    except: raise HTTPException(401)

def seed():
    for i in range(12):
        pid=f"prod_{i+1:03d}"
        PRODUCTS[pid]={"id":pid,"title":f"Product {i+1}","description":f"Desc {i+1}",
                       "handle":f"product-{i+1}","thumbnail":f"img_{i+1}.jpg",
                       "variants":[{"id":f"{pid}_v1","title":"Default","prices":[{"amount":random.randint(500,9999),"currency_code":"usd"}]}],
                       "tags":[{"id":f"tag_{i%3}","value":["clothing","electronics","home"][i%3]}],
                       "type":{"id":f"type_{i%2}","value":["physical","digital"][i%2]},
                       "collection_id":f"col_{i%3+1:03d}","status":"published"}
    for i in range(3):
        cid=f"col_{i+1:03d}"
        COLLECTIONS[cid]={"id":cid,"title":f"Collection {i+1}","handle":f"collection-{i+1}"}
    for i in range(4):
        CATEGORIES[f"cat_{i+1:03d}"]={"id":f"cat_{i+1:03d}","name":f"Category {i+1}","handle":f"cat-{i+1}"}
    for code in ["usd","eur","gbp"]:
        CURRENCIES[code]={"code":code,"name":code.upper(),"symbol":"$€£"["usd eur gbp".split().index(code)]}
    REGIONS["reg_us"]={"id":"reg_us","name":"US","currency_code":"usd","countries":[{"iso_2":"us"}]}
    REGIONS["reg_eu"]={"id":"reg_eu","name":"Europe","currency_code":"eur","countries":[{"iso_2":"de"},{"iso_2":"fr"}]}
    for email,pw,name in [("customer@store.com","shop123","Jane Doe")]:
        cid=f"cust_{uuid.uuid4().hex[:8]}"
        CUSTOMERS[cid]={"id":cid,"email":email,"password_hash":_hash(pw),"first_name":name.split()[0],"last_name":name.split()[1],
                        "addresses":[],"orders":[]}
        EMAIL_INDEX[email]=cid

@asynccontextmanager
async def lifespan(app): seed(); yield
app = FastAPI(title="Medusa Store", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

# === Products (4) ===
@app.get("/store/products")
def list_products(q:Optional[str]=Query(None)): return {"products":list(PRODUCTS.values()),"count":len(PRODUCTS)}
@app.get("/store/products/{id}")
def get_product(id:str):
    if id not in PRODUCTS: raise HTTPException(404)
    return {"product":PRODUCTS[id]}
@app.get("/store/product-variants")
def list_variants(): return {"variants":[]}
@app.get("/store/product-variants/{id}")
def get_variant(id:str): return {"variant":{}}

# === Collections (2) ===
@app.get("/store/collections")
def list_collections(): return {"collections":list(COLLECTIONS.values()),"count":len(COLLECTIONS)}
@app.get("/store/collections/{id}")
def get_collection(id:str): return {"collection":COLLECTIONS.get(id,{})}

# === Categories (2) ===
@app.get("/store/product-categories")
def list_categories(): return {"product_categories":list(CATEGORIES.values())}
@app.get("/store/product-categories/{id}")
def get_category(id:str): return {"product_category":CATEGORIES.get(id,{})}

# === Tags & Types (4) ===
@app.get("/store/product-tags")
def list_tags(): return {"product_tags":[{"id":"tag_0","value":"clothing"},{"id":"tag_1","value":"electronics"},{"id":"tag_2","value":"home"}]}
@app.get("/store/product-tags/{id}")
def get_tag(id:str): return {"product_tag":{}}
@app.get("/store/product-types")
def list_types(): return {"product_types":[{"id":"type_0","value":"physical"},{"id":"type_1","value":"digital"}]}
@app.get("/store/product-types/{id}")
def get_type(id:str): return {"product_type":{}}

# === Currencies & Regions & Locales (5) ===
@app.get("/store/currencies")
def list_currencies(): return {"currencies":list(CURRENCIES.values())}
@app.get("/store/currencies/{code}")
def get_currency(code:str): return {"currency":CURRENCIES.get(code,{})}
@app.get("/store/regions")
def list_regions(): return {"regions":list(REGIONS.values())}
@app.get("/store/regions/{id}")
def get_region(id:str): return {"region":REGIONS.get(id,{})}
@app.get("/store/locales")
def get_locales(): return {"locales":[{"code":"en","name":"English"}]}

# === Shipping & Returns (4) ===
@app.get("/store/shipping-options")
def list_shipping(): return {"shipping_options":[{"id":"so_1","name":"Standard","price":500}]}
@app.post("/store/shipping-options/{id}/calculate")
def calc_shipping(id:str): return {"shipping_option":{"id":id,"amount":500}}
@app.get("/store/return-reasons")
def list_return_reasons(): return {"return_reasons":[{"id":"rr_1","value":"wrong_item"}]}
@app.get("/store/return-reasons/{id}")
def get_return_reason(id:str): return {"return_reason":{}}
@app.post("/store/returns")
def create_return(c=Depends(_auth)): return {"return":{"id":f"ret_{uuid.uuid4().hex[:8]}"}}

# === Payment (2) ===
@app.get("/store/payment-providers")
def list_payment_providers(): return {"payment_providers":[{"id":"pp_system_default"}]}
@app.post("/store/payment-collections")
def create_payment_collection(c=Depends(_auth)): return {"payment_collection":{"id":f"pc_{uuid.uuid4().hex[:8]}"}}
@app.post("/store/payment-collections/{id}/payment-sessions")
def create_session(id:str,c=Depends(_auth)): return {"payment_session":{"id":f"ps_{uuid.uuid4().hex[:8]}"}}

# === Customers (6) ===
@app.post("/store/customers")
def register_customer(): cid=f"cust_{uuid.uuid4().hex[:8]}"; return {"customer":{"id":cid}}
@app.get("/store/customers/me")
def get_me(c=Depends(_auth)): return {"customer":c}
@app.post("/store/customers/me")
def update_me(c=Depends(_auth)): return {"customer":c}
@app.get("/store/customers/me/addresses")
def list_addresses(c=Depends(_auth)): return {"addresses":c.get("addresses",[])}
@app.post("/store/customers/me/addresses")
def add_address(c=Depends(_auth)): return {"address":{"id":f"addr_{uuid.uuid4().hex[:8]}"}}
@app.get("/store/customers/me/addresses/{address_id}")
def get_address(address_id:str,c=Depends(_auth)): return {"address":{}}
@app.post("/store/customers/me/addresses/{address_id}")
def update_address(address_id:str,c=Depends(_auth)): return {"address":{}}
@app.delete("/store/customers/me/addresses/{address_id}")
def delete_address(address_id:str,c=Depends(_auth)): return {}

# === Carts (12) ===
@app.post("/store/carts")
def create_cart():
    cid=f"cart_{uuid.uuid4().hex[:8]}"
    CARTS[cid]={"id":cid,"items":[],"region_id":"reg_us","total":0}
    return {"cart":CARTS[cid]}
@app.get("/store/carts/{id}")
def get_cart(id:str):
    if id not in CARTS: raise HTTPException(404)
    return {"cart":CARTS[id]}
@app.post("/store/carts/{id}")
def update_cart(id:str): return {"cart":CARTS.get(id,{})}
@app.post("/store/carts/{id}/line-items")
def add_line_item(id:str): return {"cart":CARTS.get(id,{})}
@app.post("/store/carts/{id}/line-items/{line_id}")
def update_line_item(id:str,line_id:str): return {"cart":CARTS.get(id,{})}
@app.delete("/store/carts/{id}/line-items/{line_id}")
def delete_line_item(id:str,line_id:str): return {"cart":CARTS.get(id,{})}
@app.post("/store/carts/{id}/promotions")
def add_promotion(id:str): return {"cart":CARTS.get(id,{})}
@app.delete("/store/carts/{id}/promotions")
def remove_promotion(id:str): return {"cart":CARTS.get(id,{})}
@app.post("/store/carts/{id}/shipping-methods")
def add_shipping(id:str): return {"cart":CARTS.get(id,{})}
@app.post("/store/carts/{id}/taxes")
def calc_taxes(id:str): return {"cart":CARTS.get(id,{})}
@app.post("/store/carts/{id}/customer")
def set_customer(id:str): return {"cart":CARTS.get(id,{})}
@app.post("/store/carts/{id}/complete")
def complete_cart(id:str):
    oid=f"ord_{uuid.uuid4().hex[:8]}"
    ORDERS[oid]={"id":oid,"cart_id":id,"status":"completed"}
    return {"type":"order","data":ORDERS[oid]}

# === Orders (6) ===
@app.get("/store/orders")
def list_orders(c=Depends(_auth)): return {"orders":list(ORDERS.values()),"count":len(ORDERS)}
@app.get("/store/orders/{id}")
def get_order(id:str,c=Depends(_auth)): return {"order":ORDERS.get(id,{})}
@app.post("/store/orders/{id}/transfer/request")
def transfer_request(id:str,c=Depends(_auth)): return {"order":ORDERS.get(id,{})}
@app.post("/store/orders/{id}/transfer/accept")
def transfer_accept(id:str,c=Depends(_auth)): return {"order":ORDERS.get(id,{})}
@app.post("/store/orders/{id}/transfer/decline")
def transfer_decline(id:str,c=Depends(_auth)): return {"order":ORDERS.get(id,{})}
@app.post("/store/orders/{id}/transfer/cancel")
def transfer_cancel(id:str,c=Depends(_auth)): return {"order":ORDERS.get(id,{})}
