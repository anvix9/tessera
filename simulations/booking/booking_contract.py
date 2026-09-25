"""
Subway Booking Contract - Hand-crafted contract for the booking simulation
"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "core" / "contract"))

from schema import (
    SubwayContract, ContractTier,
    ScreenDefinition, DataField,
    ActionDefinition, ActionParameter, ActionPermission,
    RateLimit, DataTerms, DataRetention,
    ActionTrustRequirement, AgentTrust,
)


def build_booking_contract() -> SubwayContract:

    # ── Screen: Auth Gate (entry point) ──
    auth_screen = ScreenDefinition(
        id="auth_gate",
        name="Authentication",
        description="Login or register to access booking features. "
                    "Hotel and room browsing is available without login. "
                    "Making reservations requires authentication. "
                    "Test accounts: alice@example.com/password123, bob@example.com/securepass",
        data_fields=[
            DataField(name="logged_in", type="bool", description="Whether logged in"),
        ],
        actions=[
            ActionDefinition(
                id="login",
                name="Login",
                description="Login with email and password.",
                parameters=[
                    ActionParameter(name="email", type="string", required=True, description="Email"),
                    ActionParameter(name="password", type="string", required=True, description="Password"),
                ],
                transitions_to="hotel_search",
                api_endpoint="/api/auth/login",
                api_method="POST",
            ),
            ActionDefinition(
                id="register",
                name="Register",
                description="Create a new account.",
                parameters=[
                    ActionParameter(name="email", type="string", required=True, description="Email"),
                    ActionParameter(name="password", type="string", required=True, description="Password"),
                    ActionParameter(name="name", type="string", required=True, description="Full name"),
                ],
                transitions_to="hotel_search",
                api_endpoint="/api/auth/register",
                api_method="POST",
            ),
            ActionDefinition(
                id="browse_without_login",
                name="Browse without login",
                description="Browse hotels and rooms without logging in. Cannot make reservations.",
                transitions_to="hotel_search",
            ),
        ],
    )

    # ── Screen: Hotel Search ──
    search_screen = ScreenDefinition(
        id="hotel_search",
        name="Hotel search",
        description="Search hotels by city, dates, guests, and price.",
        data_fields=[
            DataField(name="hotels", type="list", description="List of matching hotels"),
            DataField(name="total", type="int", description="Total results"),
        ],
        actions=[
            ActionDefinition(
                id="search_hotels",
                name="Search hotels",
                description="Search for hotels with optional filters.",
                parameters=[
                    ActionParameter(name="city", type="enum", required=False,
                                    description="City to search in",
                                    enum_values=["new_york", "paris", "tokyo", "london", "mexico_city"]),
                    ActionParameter(name="check_in", type="string", required=False,
                                    description="Check-in date in YYYY-MM-DD format"),
                    ActionParameter(name="check_out", type="string", required=False,
                                    description="Check-out date in YYYY-MM-DD format"),
                    ActionParameter(name="guests", type="int", required=False,
                                    description="Number of guests", min_value=1, max_value=6),
                    ActionParameter(name="min_price", type="float", required=False,
                                    description="Minimum price per night"),
                    ActionParameter(name="max_price", type="float", required=False,
                                    description="Maximum price per night"),
                    ActionParameter(name="sort_by", type="enum", required=False,
                                    description="Sort order",
                                    enum_values=["rating", "price_asc", "price_desc"]),
                ],
                transitions_to="hotel_search",
                api_endpoint="/api/hotels",
                api_method="GET",
            ),
            ActionDefinition(
                id="view_hotel",
                name="View hotel details",
                description="View a specific hotel's details and amenities.",
                parameters=[
                    ActionParameter(name="hotel_id", type="string", required=True,
                                    description="Hotel ID to view"),
                ],
                transitions_to="hotel_detail",
                api_endpoint="/api/hotels/{hotel_id}",
                api_method="GET",
            ),
            ActionDefinition(
                id="view_rooms_direct",
                name="View rooms (shortcut)",
                description="Jump directly to room list for a hotel. Skips hotel detail screen.",
                parameters=[
                    ActionParameter(name="hotel_id", type="string", required=True, description="Hotel ID"),
                    ActionParameter(name="check_in", type="string", required=False, description="Check-in YYYY-MM-DD"),
                    ActionParameter(name="check_out", type="string", required=False, description="Check-out YYYY-MM-DD"),
                    ActionParameter(name="guests", type="int", required=False, description="Number of guests"),
                ],
                transitions_to="room_list",
                api_endpoint="/api/hotels/{hotel_id}/rooms",
                api_method="GET",
            ),
            ActionDefinition(
                id="quick_book",
                name="Quick book (shortcut)",
                description="Book a room directly if you already know the room_id. "
                            "Skips hotel detail and room list screens. Requires login.",
                permission=ActionPermission.REQUIRES_CONFIRMATION,
                parameters=[
                    ActionParameter(name="room_id", type="string", required=True, description="Room ID to book"),
                    ActionParameter(name="check_in", type="string", required=True, description="Check-in YYYY-MM-DD"),
                    ActionParameter(name="check_out", type="string", required=True, description="Check-out YYYY-MM-DD"),
                    ActionParameter(name="guest_name", type="string", required=True, description="Guest name"),
                    ActionParameter(name="guest_email", type="string", required=True, description="Guest email"),
                    ActionParameter(name="guest_phone", type="string", required=False, description="Guest phone"),
                ],
                transitions_to="reservation_confirmation",
                api_endpoint="/api/reservations",
                api_method="POST",
            ),
        ]
    )

    # ── Screen: Hotel Detail ──
    hotel_detail_screen = ScreenDefinition(
        id="hotel_detail",
        name="Hotel detail",
        description="Hotel info with amenities. View rooms to check availability.",
        parameters=["hotel_id"],
        data_fields=[
            DataField(name="name", type="string", description="Hotel name"),
            DataField(name="city", type="string", description="City"),
            DataField(name="rating", type="float", description="Rating out of 5"),
            DataField(name="description", type="string", description="Hotel description"),
            DataField(name="amenities", type="list", description="Available amenities"),
            DataField(name="price_min", type="float", description="Cheapest room per night"),
            DataField(name="price_max", type="float", description="Most expensive room per night"),
        ],
        actions=[
            ActionDefinition(
                id="view_rooms",
                name="View available rooms",
                description="List rooms at this hotel with availability for your dates.",
                parameters=[
                    ActionParameter(name="hotel_id", type="string", required=True,
                                    description="Hotel ID"),
                    ActionParameter(name="check_in", type="string", required=False,
                                    description="Check-in date YYYY-MM-DD"),
                    ActionParameter(name="check_out", type="string", required=False,
                                    description="Check-out date YYYY-MM-DD"),
                    ActionParameter(name="guests", type="int", required=False,
                                    description="Number of guests"),
                ],
                transitions_to="room_list",
                api_endpoint="/api/hotels/{hotel_id}/rooms",
                api_method="GET",
            ),
            ActionDefinition(
                id="back_to_hotel_search",
                name="Back to search",
                description="Return to hotel search results.",
                transitions_to="hotel_search",
            ),
        ],
        parent="hotel_search",
    )

    # ── Screen: Room List ──
    room_list_screen = ScreenDefinition(
        id="room_list",
        name="Room list",
        description="Available rooms at the hotel with prices and availability.",
        data_fields=[
            DataField(name="rooms", type="list", description="Rooms with availability and pricing"),
            DataField(name="hotel", type="object", description="Hotel info"),
        ],
        actions=[
            ActionDefinition(
                id="view_room",
                name="View room details",
                description="View detailed info about a specific room.",
                parameters=[
                    ActionParameter(name="room_id", type="string", required=True,
                                    description="Room ID to view"),
                    ActionParameter(name="check_in", type="string", required=False,
                                    description="Check-in date"),
                    ActionParameter(name="check_out", type="string", required=False,
                                    description="Check-out date"),
                ],
                transitions_to="room_detail",
                api_endpoint="/api/rooms/{room_id}",
                api_method="GET",
            ),
            ActionDefinition(
                id="book_room",
                name="Book a room",
                description="Make a reservation for a specific room.",
                permission=ActionPermission.REQUIRES_CONFIRMATION,
                parameters=[
                    ActionParameter(name="room_id", type="string", required=True,
                                    description="Room ID to book"),
                    ActionParameter(name="check_in", type="string", required=True,
                                    description="Check-in date YYYY-MM-DD"),
                    ActionParameter(name="check_out", type="string", required=True,
                                    description="Check-out date YYYY-MM-DD"),
                    ActionParameter(name="guest_name", type="string", required=True,
                                    description="Guest full name"),
                    ActionParameter(name="guest_email", type="string", required=True,
                                    description="Guest email address"),
                    ActionParameter(name="guest_phone", type="string", required=False,
                                    description="Guest phone number"),
                ],
                transitions_to="reservation_confirmation",
                api_endpoint="/api/reservations",
                api_method="POST",
            ),
            ActionDefinition(
                id="back_to_hotel",
                name="Back to hotel",
                description="Return to hotel detail.",
                transitions_to="hotel_detail",
            ),
        ],
        parent="hotel_detail",
    )

    # ── Screen: Room Detail ──
    room_detail_screen = ScreenDefinition(
        id="room_detail",
        name="Room detail",
        description="Detailed room info with availability calendar.",
        parameters=["room_id"],
        data_fields=[
            DataField(name="name", type="string", description="Room name"),
            DataField(name="room_type", type="string", description="Room type"),
            DataField(name="price_per_night", type="float", description="Price per night"),
            DataField(name="max_guests", type="int", description="Maximum guests"),
            DataField(name="available", type="bool", description="Available for selected dates"),
            DataField(name="calendar", type="list", description="14-day availability calendar"),
        ],
        actions=[
            ActionDefinition(
                id="book_this_room",
                name="Book this room",
                description="Make a reservation for this room.",
                permission=ActionPermission.REQUIRES_CONFIRMATION,
                parameters=[
                    ActionParameter(name="room_id", type="string", required=True, description="Room ID"),
                    ActionParameter(name="check_in", type="string", required=True, description="Check-in date YYYY-MM-DD"),
                    ActionParameter(name="check_out", type="string", required=True, description="Check-out date YYYY-MM-DD"),
                    ActionParameter(name="guest_name", type="string", required=True, description="Guest name"),
                    ActionParameter(name="guest_email", type="string", required=True, description="Guest email"),
                ],
                transitions_to="reservation_confirmation",
                api_endpoint="/api/reservations",
                api_method="POST",
            ),
            ActionDefinition(
                id="back_to_rooms",
                name="Back to room list",
                description="Return to room list.",
                transitions_to="room_list",
            ),
        ],
        parent="room_list",
    )

    # ── Screen: Reservation Confirmation ──
    confirmation_screen = ScreenDefinition(
        id="reservation_confirmation",
        name="Reservation confirmation",
        description="Reservation details and status.",
        data_fields=[
            DataField(name="reservation_id", type="string", description="Reservation ID"),
            DataField(name="status", type="string", description="Reservation status"),
            DataField(name="total_price", type="float", description="Total price"),
            DataField(name="message", type="string", description="Confirmation message"),
        ],
        actions=[
            ActionDefinition(
                id="check_reservation",
                name="Check reservation status",
                description="Check the status of a reservation.",
                parameters=[
                    ActionParameter(name="res_id", type="string", required=True,
                                    description="Reservation ID"),
                ],
                transitions_to="reservation_confirmation",
                api_endpoint="/api/reservations/{res_id}",
                api_method="GET",
            ),
            ActionDefinition(
                id="cancel_reservation",
                name="Cancel reservation",
                description="Cancel a reservation and free the dates.",
                permission=ActionPermission.REQUIRES_CONFIRMATION,
                parameters=[
                    ActionParameter(name="res_id", type="string", required=True,
                                    description="Reservation ID to cancel"),
                ],
                transitions_to="reservation_confirmation",
                api_endpoint="/api/reservations/{res_id}/cancel",
                api_method="POST",
            ),
            ActionDefinition(
                id="new_search",
                name="New search",
                description="Start a new hotel search.",
                transitions_to="hotel_search",
            ),
        ],
    )

    # ── Assemble Contract ──
    contract = SubwayContract(
        contract_id="subway_booking_v2_auth",
        version="0.2.0",
        site_name="SubwayStay Hotel Booking (with Auth)",
        site_url="http://localhost:8002",
        description="Hotel booking service with authentication. Agents must login or register "
                    "before making reservations. Hotel and room browsing is public. "
                    "Test accounts: alice@example.com/password123, bob@example.com/securepass",
        tier=ContractTier.STANDARD,

        screens=[auth_screen, search_screen, hotel_detail_screen, room_list_screen,
                 room_detail_screen, confirmation_screen],
        entry_screen="auth_gate",

        rate_limits=RateLimit(
            requests_per_minute=30,
            requests_per_hour=500,
            requests_per_day=5000,
            max_concurrent_sessions=1,
        ),

        data_terms=DataTerms(
            default_retention=DataRetention.SESSION,
            field_overrides={
                "guest_email": DataRetention.NONE,
                "guest_phone": DataRetention.NONE,
            },
            allow_aggregation=False,
            allow_storage=False,
        ),

        prohibited_actions=["bulk_scrape", "access_admin", "modify_reviews"],
        required_confirmations=["book_room", "book_this_room", "cancel_reservation"],

        action_trust_requirements=[
            ActionTrustRequirement(action_id="book_room", min_trust_level=AgentTrust.VERIFIED),
            ActionTrustRequirement(action_id="book_this_room", min_trust_level=AgentTrust.VERIFIED),
            ActionTrustRequirement(action_id="cancel_reservation", min_trust_level=AgentTrust.VERIFIED),
        ],
        default_trust_for_actions=AgentTrust.IDENTIFIED,
        trust_overrides={},

        require_identification=True,
        allowed_purposes=["hotel_search", "booking", "research", "price_comparison", "purchase"],
        blocked_providers=[],
        log_all_actions=True,
        log_data_access=True,
    )

    return contract


if __name__ == "__main__":
    contract = build_booking_contract()
    output = str(Path(__file__).parent / "contract.json")
    with open(output, "w") as f:
        json.dump(contract.model_dump(mode="json"), f, indent=2)
    print(f"Booking contract exported to {output}")
    print(f"  Screens: {len(contract.screens)}")
    print(f"  Actions: {sum(len(s.actions) for s in contract.screens)}")
