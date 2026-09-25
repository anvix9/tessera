"""
Subway Booking Simulation - Data Models & In-Memory Store

A hotel booking site with:
- Hotels with rooms of different types
- Date-based availability (rooms blocked on reserved dates)
- Reservation lifecycle: pending → confirmed → cancelled
- Guest info required for booking
"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
import uuid
from datetime import datetime, date, timedelta


# ── Enums ──

class RoomType(str, Enum):
    SINGLE = "single"
    DOUBLE = "double"
    SUITE = "suite"
    FAMILY = "family"


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class City(str, Enum):
    NEW_YORK = "new_york"
    PARIS = "paris"
    TOKYO = "tokyo"
    LONDON = "london"
    MEXICO_CITY = "mexico_city"


# ── Models ──

class Hotel(BaseModel):
    id: str
    name: str
    city: City
    description: str
    rating: float = Field(ge=0, le=5)
    review_count: int = 0
    amenities: list[str] = []
    price_min: float = 0        # Cheapest room per night
    price_max: float = 0        # Most expensive room per night


class Room(BaseModel):
    id: str
    hotel_id: str
    room_type: RoomType
    name: str
    description: str
    price_per_night: float
    max_guests: int
    amenities: list[str] = []


class Availability(BaseModel):
    room_id: str
    date: str                   # ISO date string
    available: bool = True


class GuestInfo(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None


class Reservation(BaseModel):
    id: str
    hotel_id: str
    room_id: str
    guest: GuestInfo
    check_in: str               # ISO date
    check_out: str              # ISO date
    nights: int
    total_price: float
    status: ReservationStatus = ReservationStatus.PENDING
    created_at: str = ""


# ── Request/Response Schemas ──

class SearchHotelsRequest(BaseModel):
    city: Optional[City] = None
    check_in: Optional[str] = None      # ISO date
    check_out: Optional[str] = None     # ISO date
    guests: Optional[int] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    sort_by: Optional[str] = "rating"   # rating, price_asc, price_desc


class HotelListResponse(BaseModel):
    hotels: list[Hotel]
    total: int


class RoomListResponse(BaseModel):
    rooms: list[dict]           # Room + availability info
    hotel: Hotel
    check_in: Optional[str] = None
    check_out: Optional[str] = None


class BookingRequest(BaseModel):
    room_id: str
    check_in: str
    check_out: str
    guest_name: str
    guest_email: str
    guest_phone: Optional[str] = None


class ReservationResponse(BaseModel):
    reservation: Reservation
    message: str = ""


# ── In-Memory Database ──

HOTELS: dict[str, Hotel] = {}
ROOMS: dict[str, Room] = {}
RESERVATIONS: dict[str, Reservation] = {}
BLOCKED_DATES: dict[str, set[str]] = {}    # room_id -> set of blocked date strings


def seed_data():
    """Populate with sample hotels and rooms."""
    hotels_data = [
        ("The Grand Central", City.NEW_YORK, "Luxury hotel in Midtown Manhattan with skyline views.", 4.5, 2341,
         ["wifi", "pool", "gym", "spa", "restaurant", "bar", "concierge"]),
        ("Brooklyn Bridge Inn", City.NEW_YORK, "Boutique hotel near Brooklyn Bridge with rooftop terrace.", 4.2, 876,
         ["wifi", "gym", "rooftop", "breakfast"]),
        ("Hotel Le Marais", City.PARIS, "Charming hotel in the heart of Le Marais district.", 4.6, 1543,
         ["wifi", "breakfast", "bar", "garden", "concierge"]),
        ("Eiffel View Palace", City.PARIS, "Premium hotel with direct Eiffel Tower views.", 4.8, 3210,
         ["wifi", "pool", "spa", "restaurant", "bar", "gym", "concierge"]),
        ("Tokyo Station Hotel", City.TOKYO, "Historic hotel inside Tokyo Station with modern amenities.", 4.4, 1892,
         ["wifi", "restaurant", "gym", "onsen", "concierge"]),
        ("Shibuya Capsule Plus", City.TOKYO, "Modern capsule hotel with premium pods and coworking space.", 3.9, 2105,
         ["wifi", "coworking", "laundry", "lounge"]),
        ("The Thames House", City.LONDON, "Georgian townhouse hotel near the Thames.", 4.3, 1204,
         ["wifi", "breakfast", "bar", "garden"]),
        ("Covent Garden Suites", City.LONDON, "All-suite hotel in the heart of Covent Garden.", 4.7, 987,
         ["wifi", "gym", "restaurant", "bar", "concierge", "theater_tickets"]),
        ("Condesa Boutique", City.MEXICO_CITY, "Art deco hotel in the trendy Condesa neighborhood.", 4.4, 756,
         ["wifi", "pool", "rooftop_bar", "breakfast", "bikes"]),
        ("Zocalo Grand", City.MEXICO_CITY, "Historic hotel overlooking the main plaza.", 4.1, 1432,
         ["wifi", "restaurant", "spa", "rooftop", "concierge"]),
    ]

    rooms_data = [
        # (hotel_index, room_type, name, description, price, max_guests, amenities)
        (0, RoomType.SINGLE, "Standard King", "King bed, city view", 249.99, 2, ["king_bed", "city_view", "minibar"]),
        (0, RoomType.DOUBLE, "Double Queen", "Two queen beds, park view", 349.99, 4, ["queen_beds", "park_view", "minibar"]),
        (0, RoomType.SUITE, "Executive Suite", "Living room + bedroom, panoramic view", 599.99, 3, ["king_bed", "living_room", "panoramic_view", "minibar", "jacuzzi"]),
        (1, RoomType.SINGLE, "Cozy Single", "Queen bed, exposed brick", 149.99, 2, ["queen_bed", "exposed_brick"]),
        (1, RoomType.DOUBLE, "Brooklyn Double", "Two full beds, bridge view", 199.99, 3, ["full_beds", "bridge_view"]),
        (2, RoomType.SINGLE, "Chambre Classique", "Queen bed, courtyard view", 189.99, 2, ["queen_bed", "courtyard_view"]),
        (2, RoomType.DOUBLE, "Chambre Superieure", "King bed, balcony", 279.99, 2, ["king_bed", "balcony", "minibar"]),
        (2, RoomType.SUITE, "Suite Marais", "Two rooms, antique furnishings", 449.99, 4, ["king_bed", "living_room", "antiques", "minibar"]),
        (3, RoomType.SINGLE, "Tour View Room", "Queen bed, Eiffel Tower view", 329.99, 2, ["queen_bed", "eiffel_view"]),
        (3, RoomType.SUITE, "Penthouse Suite", "Full floor, 360-degree views", 1299.99, 4, ["king_bed", "living_room", "terrace", "butler", "champagne"]),
        (4, RoomType.SINGLE, "Classic Room", "Twin or double, station-side", 179.99, 2, ["double_bed", "station_view"]),
        (4, RoomType.DOUBLE, "Superior Room", "King bed, garden view", 259.99, 2, ["king_bed", "garden_view", "tea_set"]),
        (5, RoomType.SINGLE, "Premium Pod", "Upgraded capsule with workspace", 59.99, 1, ["pod", "workspace", "locker"]),
        (5, RoomType.SINGLE, "Deluxe Pod", "Extra-wide capsule with entertainment", 79.99, 1, ["xl_pod", "entertainment", "locker"]),
        (6, RoomType.SINGLE, "Georgian Room", "Classic decor, river view", 199.99, 2, ["queen_bed", "river_view"]),
        (6, RoomType.DOUBLE, "Thames Suite", "Sitting area, premium bath", 349.99, 3, ["king_bed", "sitting_area", "premium_bath"]),
        (7, RoomType.SUITE, "West End Suite", "Luxury suite with theater district views", 499.99, 2, ["king_bed", "living_room", "theater_view", "minibar"]),
        (7, RoomType.FAMILY, "Family Suite", "Two bedrooms, kitchenette", 599.99, 5, ["two_bedrooms", "kitchenette", "play_area"]),
        (8, RoomType.SINGLE, "Art Deco Room", "Original features, balcony", 119.99, 2, ["queen_bed", "balcony", "art_deco"]),
        (8, RoomType.DOUBLE, "Condesa Suite", "Living area, rooftop access", 189.99, 3, ["king_bed", "living_area", "rooftop_access"]),
        (9, RoomType.SINGLE, "Plaza View", "Overlooking the Zocalo", 99.99, 2, ["double_bed", "plaza_view"]),
        (9, RoomType.SUITE, "Presidential Suite", "Two floors, colonial decor", 399.99, 4, ["king_bed", "two_floors", "colonial_decor", "butler"]),
    ]

    for i, (name, city, desc, rating, reviews, amenities) in enumerate(hotels_data):
        hid = f"hotel_{i+1:03d}"
        HOTELS[hid] = Hotel(
            id=hid, name=name, city=city, description=desc,
            rating=rating, review_count=reviews, amenities=amenities,
        )

    for i, (hotel_idx, rtype, name, desc, price, guests, amenities) in enumerate(rooms_data):
        rid = f"room_{i+1:03d}"
        hid = f"hotel_{hotel_idx+1:03d}"
        ROOMS[rid] = Room(
            id=rid, hotel_id=hid, room_type=rtype,
            name=name, description=desc,
            price_per_night=price, max_guests=guests,
            amenities=amenities,
        )
        BLOCKED_DATES[rid] = set()

    # Set price ranges on hotels
    for hid, hotel in HOTELS.items():
        hotel_rooms = [r for r in ROOMS.values() if r.hotel_id == hid]
        if hotel_rooms:
            hotel.price_min = min(r.price_per_night for r in hotel_rooms)
            hotel.price_max = max(r.price_per_night for r in hotel_rooms)

    # Pre-block some dates to simulate existing reservations
    today = date.today()
    BLOCKED_DATES["room_001"].update([
        (today + timedelta(days=d)).isoformat() for d in range(3, 7)
    ])
    BLOCKED_DATES["room_006"].update([
        (today + timedelta(days=d)).isoformat() for d in range(1, 4)
    ])
    BLOCKED_DATES["room_013"].update([
        (today + timedelta(days=d)).isoformat() for d in range(0, 10)
    ])


def check_availability(room_id: str, check_in: str, check_out: str) -> bool:
    """Check if a room is available for the given date range."""
    if room_id not in ROOMS:
        return False
    blocked = BLOCKED_DATES.get(room_id, set())
    ci = date.fromisoformat(check_in)
    co = date.fromisoformat(check_out)
    current = ci
    while current < co:
        if current.isoformat() in blocked:
            return False
        current += timedelta(days=1)
    return True


def block_dates(room_id: str, check_in: str, check_out: str):
    """Block dates for a reservation."""
    ci = date.fromisoformat(check_in)
    co = date.fromisoformat(check_out)
    current = ci
    while current < co:
        BLOCKED_DATES.setdefault(room_id, set()).add(current.isoformat())
        current += timedelta(days=1)


def create_reservation(room_id: str, check_in: str, check_out: str, guest: GuestInfo) -> Reservation:
    """Create a new reservation."""
    room = ROOMS[room_id]
    ci = date.fromisoformat(check_in)
    co = date.fromisoformat(check_out)
    nights = (co - ci).days

    res_id = f"res_{uuid.uuid4().hex[:8]}"
    reservation = Reservation(
        id=res_id,
        hotel_id=room.hotel_id,
        room_id=room_id,
        guest=guest,
        check_in=check_in,
        check_out=check_out,
        nights=nights,
        total_price=round(room.price_per_night * nights, 2),
        status=ReservationStatus.CONFIRMED,
        created_at=datetime.utcnow().isoformat(),
    )
    RESERVATIONS[res_id] = reservation
    block_dates(room_id, check_in, check_out)
    return reservation
