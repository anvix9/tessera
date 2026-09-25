"""
Subway Booking Simulation - FastAPI Application (Level 2: Auth & Sessions)

Public endpoints (no auth):
  GET  /api/hotels              - Search hotels by city, dates, guests
  GET  /api/hotels/{id}         - Hotel detail
  GET  /api/hotels/{id}/rooms   - List rooms with availability for dates
  GET  /api/rooms/{id}          - Room detail with availability calendar
  POST /api/auth/register       - Create account
  POST /api/auth/login          - Login, get JWT token

Protected endpoints (require Authorization: Bearer <token>):
  POST /api/reservations        - Create a reservation (book a room)
  GET  /api/reservations/{id}   - Check reservation status
  POST /api/reservations/{id}/cancel - Cancel a reservation
  GET  /api/auth/profile        - User profile
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.responses import HTMLResponse
from typing import Optional
from datetime import date, timedelta

from models import (
    HOTELS, ROOMS, RESERVATIONS, BLOCKED_DATES,
    seed_data, check_availability, create_reservation,
    Hotel, Room, City, RoomType, GuestInfo, ReservationStatus,
    HotelListResponse, RoomListResponse, BookingRequest, ReservationResponse,
)
from auth import (
    seed_users, register_user, authenticate_user,
    get_user_from_token, create_token,
    RegisterRequest, LoginRequest, AuthResponse, User,
)


@asynccontextmanager
async def lifespan(app):
    seed_data()
    seed_users()
    yield


app = FastAPI(
    title="Subway Booking Simulation",
    description="Simulated hotel booking site with authentication (Level 2)",
    version="0.2.0",
    lifespan=lifespan,
)


# ── Auth Dependency ──

def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required. Use: Authorization: Bearer <token>")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid format. Use: Bearer <token>")
    user = get_user_from_token(parts[1])
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


# ── Auth Endpoints ──

@app.post("/api/auth/register", response_model=AuthResponse)
def register(req: RegisterRequest):
    if not req.email or not req.password or not req.name:
        raise HTTPException(status_code=400, detail="Email, password, and name required")
    try:
        user = register_user(req.email, req.password, req.name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    token = create_token(user)
    return AuthResponse(token=token, user_id=user.id, name=user.name, email=user.email,
                        message=f"Account created for {user.name}")


@app.post("/api/auth/login", response_model=AuthResponse)
def login(req: LoginRequest):
    user = authenticate_user(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user)
    return AuthResponse(token=token, user_id=user.id, name=user.name, email=user.email,
                        message=f"Welcome back, {user.name}!")


# ── Hotel Endpoints ──

@app.get("/api/hotels")
def search_hotels(
    city: Optional[City] = Query(None, description="Filter by city"),
    check_in: Optional[str] = Query(None, description="Check-in date (ISO format: YYYY-MM-DD)"),
    check_out: Optional[str] = Query(None, description="Check-out date (ISO format: YYYY-MM-DD)"),
    guests: Optional[int] = Query(None, ge=1, description="Number of guests"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price per night"),
    max_price: Optional[float] = Query(None, description="Maximum price per night"),
    sort_by: Optional[str] = Query("rating", description="Sort: rating, price_asc, price_desc"),
):
    """Search hotels with filters. Shows only hotels with available rooms for the given dates."""
    results = list(HOTELS.values())

    # Filter by city
    if city:
        results = [h for h in results if h.city == city]

    # Filter by price range
    if min_price is not None:
        try:
            results = [h for h in results if h.price_max >= float(min_price)]
        except (ValueError, TypeError):
            pass
    if max_price is not None:
        try:
            results = [h for h in results if h.price_min <= float(max_price)]
        except (ValueError, TypeError):
            pass

    # Filter by availability if dates provided
    if check_in and check_out:
        available_hotels = []
        for hotel in results:
            hotel_rooms = [r for r in ROOMS.values() if r.hotel_id == hotel.id]
            has_available = any(
                check_availability(r.id, check_in, check_out)
                and (guests is None or r.max_guests >= guests)
                for r in hotel_rooms
            )
            if has_available:
                available_hotels.append(hotel)
        results = available_hotels

    # Sort
    if sort_by == "price_asc":
        results.sort(key=lambda h: h.price_min)
    elif sort_by == "price_desc":
        results.sort(key=lambda h: h.price_max, reverse=True)
    elif sort_by == "rating":
        results.sort(key=lambda h: h.rating, reverse=True)

    # Enrich with cheapest available room per hotel (enables quick_book shortcut)
    enriched = []
    for hotel in results:
        h_data = hotel.model_dump()
        hotel_rooms = [r for r in ROOMS.values() if r.hotel_id == hotel.id]
        if guests:
            hotel_rooms = [r for r in hotel_rooms if r.max_guests >= guests]
        if check_in and check_out:
            hotel_rooms = [r for r in hotel_rooms if check_availability(r.id, check_in, check_out)]
        hotel_rooms.sort(key=lambda r: r.price_per_night)
        if hotel_rooms:
            cheapest = hotel_rooms[0]
            h_data["cheapest_room"] = {
                "room_id": cheapest.id,
                "name": cheapest.name,
                "price_per_night": cheapest.price_per_night,
                "max_guests": cheapest.max_guests,
            }
            if check_in and check_out:
                from datetime import date as date_cls
                nights = (date_cls.fromisoformat(check_out) - date_cls.fromisoformat(check_in)).days
                h_data["cheapest_room"]["total_price"] = round(cheapest.price_per_night * nights, 2)
                h_data["cheapest_room"]["nights"] = nights
        enriched.append(h_data)

    return {"hotels": enriched, "total": len(enriched)}


@app.get("/api/hotels/{hotel_id}", response_model=Hotel)
def get_hotel(hotel_id: str):
    """Get hotel details."""
    if hotel_id not in HOTELS:
        raise HTTPException(status_code=404, detail="Hotel not found")
    return HOTELS[hotel_id]


@app.get("/api/hotels/{hotel_id}/rooms", response_model=RoomListResponse)
def get_hotel_rooms(
    hotel_id: str,
    check_in: Optional[str] = Query(None, description="Check-in date (ISO)"),
    check_out: Optional[str] = Query(None, description="Check-out date (ISO)"),
    guests: Optional[int] = Query(None, ge=1, description="Number of guests"),
):
    """List rooms for a hotel with availability status."""
    if hotel_id not in HOTELS:
        raise HTTPException(status_code=404, detail="Hotel not found")

    hotel = HOTELS[hotel_id]
    hotel_rooms = [r for r in ROOMS.values() if r.hotel_id == hotel_id]

    # Filter by guest capacity
    if guests:
        hotel_rooms = [r for r in hotel_rooms if r.max_guests >= guests]

    rooms_with_availability = []
    for room in hotel_rooms:
        room_data = room.model_dump()
        if check_in and check_out:
            available = check_availability(room.id, check_in, check_out)
            nights = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
            room_data["available"] = available
            room_data["nights"] = nights
            room_data["total_price"] = round(room.price_per_night * nights, 2)
        else:
            room_data["available"] = True
            room_data["nights"] = None
            room_data["total_price"] = None
        rooms_with_availability.append(room_data)

    return RoomListResponse(
        rooms=rooms_with_availability, hotel=hotel,
        check_in=check_in, check_out=check_out,
    )


@app.get("/api/rooms/{room_id}")
def get_room(
    room_id: str,
    check_in: Optional[str] = Query(None, description="Check-in date (ISO)"),
    check_out: Optional[str] = Query(None, description="Check-out date (ISO)"),
):
    """Get room details with availability."""
    if room_id not in ROOMS:
        raise HTTPException(status_code=404, detail="Room not found")

    room = ROOMS[room_id]
    hotel = HOTELS.get(room.hotel_id)
    room_data = room.model_dump()
    room_data["hotel_name"] = hotel.name if hotel else "Unknown"
    room_data["hotel_city"] = hotel.city.value if hotel else "Unknown"

    if check_in and check_out:
        available = check_availability(room_id, check_in, check_out)
        nights = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
        room_data["available"] = available
        room_data["nights"] = nights
        room_data["total_price"] = round(room.price_per_night * nights, 2)
    else:
        room_data["available"] = None

    # Show next 14 days availability
    today = date.today()
    blocked = BLOCKED_DATES.get(room_id, set())
    calendar = []
    for i in range(14):
        d = today + timedelta(days=i)
        calendar.append({"date": d.isoformat(), "available": d.isoformat() not in blocked})
    room_data["calendar"] = calendar

    return room_data


# ── Reservation Endpoints (Protected) ──

@app.post("/api/reservations", response_model=ReservationResponse)
def book_room(req: BookingRequest, user: User = Depends(get_current_user)):
    """Create a reservation. Requires login."""
    if req.room_id not in ROOMS:
        raise HTTPException(status_code=404, detail="Room not found")

    room = ROOMS[req.room_id]

    # Validate dates
    try:
        ci = date.fromisoformat(req.check_in)
        co = date.fromisoformat(req.check_out)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if co <= ci:
        raise HTTPException(status_code=400, detail="Check-out must be after check-in")

    if ci < date.today():
        raise HTTPException(status_code=400, detail="Check-in cannot be in the past")

    nights = (co - ci).days
    if nights > 30:
        raise HTTPException(status_code=400, detail="Maximum 30 nights per reservation")

    # Check availability
    if not check_availability(req.room_id, req.check_in, req.check_out):
        raise HTTPException(
            status_code=409,
            detail=f"Room {room.name} is not available for {req.check_in} to {req.check_out}"
        )

    # Validate guest info
    if not req.guest_name or not req.guest_email:
        raise HTTPException(status_code=400, detail="Guest name and email are required")

    guest = GuestInfo(name=req.guest_name, email=req.guest_email, phone=req.guest_phone)
    reservation = create_reservation(req.room_id, req.check_in, req.check_out, guest)

    hotel = HOTELS.get(room.hotel_id)
    return ReservationResponse(
        reservation=reservation,
        message=f"Reservation confirmed! {room.name} at {hotel.name if hotel else 'hotel'} "
                f"for {nights} nights (${reservation.total_price}). "
                f"Confirmation ID: {reservation.id}"
    )


@app.get("/api/reservations/{res_id}", response_model=ReservationResponse)
def get_reservation(res_id: str, user: User = Depends(get_current_user)):
    """Check reservation status. Requires login."""
    if res_id not in RESERVATIONS:
        raise HTTPException(status_code=404, detail="Reservation not found")
    res = RESERVATIONS[res_id]
    return ReservationResponse(
        reservation=res,
        message=f"Reservation {res.id}: {res.status.value}"
    )


@app.post("/api/reservations/{res_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(res_id: str, user: User = Depends(get_current_user)):
    """Cancel a reservation and free up the dates. Requires login."""
    if res_id not in RESERVATIONS:
        raise HTTPException(status_code=404, detail="Reservation not found")

    res = RESERVATIONS[res_id]
    if res.status == ReservationStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Reservation already cancelled")

    # Free up the dates
    ci = date.fromisoformat(res.check_in)
    co = date.fromisoformat(res.check_out)
    current = ci
    while current < co:
        BLOCKED_DATES.get(res.room_id, set()).discard(current.isoformat())
        current += timedelta(days=1)

    res.status = ReservationStatus.CANCELLED

    return ReservationResponse(
        reservation=res,
        message=f"Reservation {res.id} has been cancelled. Refund will be processed."
    )


# ── HTML Frontend ──

@app.get("/", response_class=HTMLResponse)
def homepage():
    return get_frontend_html()


def get_frontend_html():
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    next_week = (date.today() + timedelta(days=7)).isoformat()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SubwayStay - Hotel Booking</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }}
  header {{ background: #1a1a2e; color: white; padding: 16px 24px; }}
  header h1 {{ font-size: 22px; }} header h1 span {{ color: #e6a817; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
  .search-bar {{ display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }}
  .search-bar select, .search-bar input, .search-bar button {{ padding: 10px 14px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; }}
  .search-bar button {{ background: #e6a817; color: #1a1a2e; border: none; font-weight: 600; cursor: pointer; }}
  .hotels {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; }}
  .hotel-card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); cursor: pointer; transition: transform 0.15s; }}
  .hotel-card:hover {{ transform: translateY(-2px); }}
  .hotel-card h3 {{ font-size: 18px; margin-bottom: 4px; }}
  .hotel-card .city {{ color: #e6a817; font-weight: 500; font-size: 13px; text-transform: uppercase; }}
  .hotel-card .price {{ font-size: 20px; font-weight: 700; margin: 8px 0; }}
  .hotel-card .meta {{ font-size: 13px; color: #777; }}
  .rating {{ color: #e6a817; }}
  .amenities {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }}
  .amenity {{ background: #f0f0f0; padding: 2px 8px; border-radius: 4px; font-size: 11px; color: #555; }}
  .view-btn {{ width: 100%; margin-top: 12px; padding: 10px; background: #1a1a2e; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }}
  .view-btn:hover {{ background: #2a2a4e; }}
  .modal-overlay {{ display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 100; justify-content: center; align-items: center; }}
  .modal-overlay.active {{ display: flex; }}
  .modal {{ background: white; border-radius: 16px; padding: 28px; max-width: 600px; width: 90%; max-height: 85vh; overflow-y: auto; }}
  .modal h2 {{ margin-bottom: 16px; }}
  .modal-close {{ float: right; background: none; border: none; font-size: 24px; cursor: pointer; color: #999; }}
  .room-card {{ border: 1px solid #eee; border-radius: 8px; padding: 16px; margin-bottom: 12px; }}
  .room-card .room-name {{ font-weight: 600; font-size: 16px; }}
  .room-card .room-price {{ font-size: 18px; font-weight: 700; color: #1a1a2e; }}
  .avail-yes {{ color: #2e7d32; font-weight: 500; }}
  .avail-no {{ color: #c62828; font-weight: 500; }}
  .book-btn {{ padding: 8px 20px; background: #e6a817; color: #1a1a2e; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; }}
  .form-group {{ margin: 10px 0; }}
  .form-group label {{ display: block; font-size: 13px; font-weight: 500; color: #555; margin-bottom: 4px; }}
  .form-group input {{ width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 8px; }}
  .confirm-btn {{ width: 100%; margin-top: 16px; padding: 14px; background: #2e7d32; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; }}
  .empty {{ text-align: center; color: #999; padding: 40px; }}
</style>
</head>
<body>
<header><h1><span>Subway</span>Stay</h1></header>
<div class="container">
  <div class="search-bar">
    <select id="city-filter">
      <option value="">All Cities</option>
      <option value="new_york">New York</option>
      <option value="paris">Paris</option>
      <option value="tokyo">Tokyo</option>
      <option value="london">London</option>
      <option value="mexico_city">Mexico City</option>
    </select>
    <input type="date" id="check-in" value="{tomorrow}">
    <input type="date" id="check-out" value="{next_week}">
    <input type="number" id="guests" value="2" min="1" max="6" style="width:80px" placeholder="Guests">
    <select id="sort-filter">
      <option value="rating">Top Rated</option>
      <option value="price_asc">Price: Low to High</option>
      <option value="price_desc">Price: High to Low</option>
    </select>
    <button onclick="searchHotels()">Search</button>
  </div>
  <div class="hotels" id="hotel-grid"></div>
</div>

<div class="modal-overlay" id="rooms-modal">
  <div class="modal">
    <button class="modal-close" onclick="closeModal('rooms-modal')">&times;</button>
    <h2 id="rooms-title">Rooms</h2>
    <div id="rooms-list"></div>
  </div>
</div>

<div class="modal-overlay" id="book-modal">
  <div class="modal">
    <button class="modal-close" onclick="closeModal('book-modal')">&times;</button>
    <h2>Complete Booking</h2>
    <div id="book-summary"></div>
    <div class="form-group"><label>Full Name</label><input id="guest-name" placeholder="Jane Doe"></div>
    <div class="form-group"><label>Email</label><input id="guest-email" type="email" placeholder="jane@example.com"></div>
    <div class="form-group"><label>Phone (optional)</label><input id="guest-phone" placeholder="+1 555 123 4567"></div>
    <button class="confirm-btn" onclick="confirmBooking()">Confirm Reservation</button>
  </div>
</div>

<div class="modal-overlay" id="confirm-modal">
  <div class="modal" style="text-align:center">
    <h2 style="color:#2e7d32" id="confirm-title">Booking Confirmed!</h2>
    <p id="confirm-msg"></p>
    <button class="view-btn" style="max-width:200px;margin:20px auto 0" onclick="location.reload()">Search Again</button>
  </div>
</div>

<script>
let selectedRoom = null;

async function searchHotels() {{
  const city = document.getElementById('city-filter').value;
  const ci = document.getElementById('check-in').value;
  const co = document.getElementById('check-out').value;
  const guests = document.getElementById('guests').value;
  const sort = document.getElementById('sort-filter').value;
  let url = `/api/hotels?sort_by=${{sort}}`;
  if (city) url += `&city=${{city}}`;
  if (ci) url += `&check_in=${{ci}}`;
  if (co) url += `&check_out=${{co}}`;
  if (guests) url += `&guests=${{guests}}`;
  const r = await fetch(url);
  const data = await r.json();
  renderHotels(data.hotels);
}}

function renderHotels(hotels) {{
  const grid = document.getElementById('hotel-grid');
  if (!hotels.length) {{ grid.innerHTML = '<div class="empty">No hotels found</div>'; return; }}
  grid.innerHTML = hotels.map(h => {{
    const stars = '\u2605'.repeat(Math.round(h.rating)) + '\u2606'.repeat(5 - Math.round(h.rating));
    return `<div class="hotel-card">
      <div class="city">${{h.city.replace('_',' ')}}</div>
      <h3>${{h.name}}</h3>
      <div class="meta"><span class="rating">${{stars}}</span> ${{h.rating}} (${{h.review_count}} reviews)</div>
      <div class="price">From $${{h.price_min}}/night</div>
      <p class="meta">${{h.description}}</p>
      <div class="amenities">${{h.amenities.slice(0,5).map(a => `<span class="amenity">${{a}}</span>`).join('')}}</div>
      <button class="view-btn" onclick="viewRooms('${{h.id}}','${{h.name}}')">View Rooms</button>
    </div>`;
  }}).join('');
}}

async function viewRooms(hotelId, hotelName) {{
  const ci = document.getElementById('check-in').value;
  const co = document.getElementById('check-out').value;
  const guests = document.getElementById('guests').value;
  let url = `/api/hotels/${{hotelId}}/rooms?`;
  if (ci) url += `check_in=${{ci}}&`;
  if (co) url += `check_out=${{co}}&`;
  if (guests) url += `guests=${{guests}}`;
  const r = await fetch(url);
  const data = await r.json();
  document.getElementById('rooms-title').textContent = hotelName + ' \u2014 Rooms';
  document.getElementById('rooms-list').innerHTML = data.rooms.map(rm => `
    <div class="room-card">
      <div class="room-name">${{rm.name}} <span style="color:#777;font-weight:400;font-size:13px">(${{rm.room_type}})</span></div>
      <p class="meta">${{rm.description}} \u2022 Max ${{rm.max_guests}} guests</p>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">
        <div>
          <div class="room-price">$${{rm.price_per_night}}/night</div>
          ${{rm.total_price ? `<div class="meta">$${{rm.total_price}} total (${{rm.nights}} nights)</div>` : ''}}
        </div>
        <div>
          ${{rm.available === true ? '<span class="avail-yes">Available</span>' : rm.available === false ? '<span class="avail-no">Unavailable</span>' : ''}}
          ${{rm.available !== false ? `<button class="book-btn" onclick="startBooking('${{rm.id}}', this)" data-name="${{rm.name}}" data-price="${{rm.price_per_night}}" data-total="${{rm.total_price || 0}}" data-nights="${{rm.nights || 0}}">Book</button>` : ''}}
        </div>
      </div>
    </div>
  `).join('');
  document.getElementById('rooms-modal').classList.add('active');
}}

function startBooking(roomId, btn) {{
  const roomName = btn.dataset.name;
  const pricePerNight = parseFloat(btn.dataset.price);
  const totalPrice = parseFloat(btn.dataset.total);
  const nights = parseInt(btn.dataset.nights);
  selectedRoom = {{ roomId, roomName, pricePerNight, totalPrice, nights }};
  const ci = document.getElementById('check-in').value;
  const co = document.getElementById('check-out').value;
  document.getElementById('book-summary').innerHTML = `
    <p><strong>${{roomName}}</strong> \u2014 $${{pricePerNight}}/night</p>
    <p>${{ci}} to ${{co}} (${{nights}} nights) \u2014 <strong>$${{totalPrice}}</strong></p>
  `;
  closeModal('rooms-modal');
  document.getElementById('book-modal').classList.add('active');
}}

async function confirmBooking() {{
  const ci = document.getElementById('check-in').value;
  const co = document.getElementById('check-out').value;
  const r = await fetch('/api/reservations', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{
      room_id: selectedRoom.roomId, check_in: ci, check_out: co,
      guest_name: document.getElementById('guest-name').value,
      guest_email: document.getElementById('guest-email').value,
      guest_phone: document.getElementById('guest-phone').value,
    }})
  }});
  if (!r.ok) {{ const err = await r.json(); alert(err.detail); return; }}
  const data = await r.json();
  closeModal('book-modal');
  document.getElementById('confirm-msg').textContent = data.message;
  document.getElementById('confirm-modal').classList.add('active');
}}

function closeModal(id) {{ document.getElementById(id).classList.remove('active'); }}
searchHotels();
</script>
</body>
</html>"""
