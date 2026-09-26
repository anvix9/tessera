"""
Tessera Phase 5b — Agent Task Definitions

Each task defines:
  - id: unique identifier
  - goal: natural language instruction for the agent
  - ground_truth: function that checks the simulation server state
  - setup: optional function to prepare the simulation before the task

To add a task: write a function that returns an AgentTask, add it to TASK_REGISTRY.

Ground truth checks query the simulation server's API directly —
no LLM judge, no subjective evaluation.
"""
import requests as http
from pathlib import Path
from evals.agent_eval import AgentTask

PROJECT_ROOT = Path(__file__).parent.parent.parent


# ══════════════════════════════════════════════
# HELPER: resolve simulation paths
# ══════════════════════════════════════════════

def _sim_path(sim_name: str) -> str:
    """Get the simulation api/ directory path."""
    return str(PROJECT_ROOT / "simulations" / sim_name / "api")


def _contract_path(sim_name: str) -> str:
    """Get the contract JSON path."""
    return str(PROJECT_ROOT / "simulations" / sim_name / "contract.json")


# ══════════════════════════════════════════════
# SHOPPING TASKS
# ══════════════════════════════════════════════

def task_shopping_browse():
    """Browse products without buying anything."""

    def ground_truth(sim_url):
        # Success = agent viewed at least one product (no purchase needed)
        # Check by verifying the server is still up (agent didn't crash it)
        try:
            r = http.get(f"{sim_url}/api/products", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    return AgentTask(
        id="shopping-browse",
        site="shopping",
        goal="Browse the store. Search for 'laptop', then view the details of the cheapest one. Do NOT buy anything.",
        contract_path=_contract_path("shopping"),
        simulation_dir=_sim_path("shopping"),
        simulation_port=8101,
        max_steps=8,
        ground_truth=ground_truth,
        category="navigation",
        description="Browse products without purchasing",
    )


def task_shopping_search_and_cart():
    """Search for a product and add it to cart."""

    def ground_truth(sim_url):
        # Check if cart has items
        try:
            # Try to get cart (may need auth token from the simulation)
            r = http.get(f"{sim_url}/api/cart", timeout=5)
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", data.get("cart", []))
                return len(items) > 0
        except Exception:
            pass
        return False

    return AgentTask(
        id="shopping-search-cart",
        site="shopping",
        goal="Search for 'headphones'. Add the first result to your cart.",
        contract_path=_contract_path("shopping"),
        simulation_dir=_sim_path("shopping"),
        simulation_port=8102,
        max_steps=10,
        ground_truth=ground_truth,
        category="interaction",
        description="Search product and add to cart",
    )


def task_shopping_full_purchase():
    """Complete a full purchase flow."""

    def ground_truth(sim_url):
        # Check if an order was placed
        try:
            r = http.get(f"{sim_url}/api/orders", timeout=5)
            if r.status_code == 200:
                data = r.json()
                orders = data.get("orders", data) if isinstance(data, dict) else data
                return len(orders) > 0
        except Exception:
            pass
        return False

    return AgentTask(
        id="shopping-full-purchase",
        site="shopping",
        goal=(
            "You need to buy a laptop. "
            "1. Login with email alice@example.com and password password123. "
            "2. Search for 'laptop'. "
            "3. Add the cheapest one to your cart. "
            "4. Proceed to checkout and place the order."
        ),
        contract_path=_contract_path("shopping"),
        simulation_dir=_sim_path("shopping"),
        simulation_port=8103,
        max_steps=15,
        ground_truth=ground_truth,
        category="transaction",
        description="Complete purchase: login → search → cart → checkout",
    )


# ══════════════════════════════════════════════
# BOOKING TASKS
# ══════════════════════════════════════════════

def task_booking_search():
    """Search for available rooms."""

    def ground_truth(sim_url):
        try:
            r = http.get(f"{sim_url}/api/rooms", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    return AgentTask(
        id="booking-search",
        site="booking",
        goal="Search for available rooms. View the details of at least one room.",
        contract_path=_contract_path("booking"),
        simulation_dir=_sim_path("booking"),
        simulation_port=8104,
        max_steps=8,
        ground_truth=ground_truth,
        category="navigation",
        description="Search and view rooms",
    )


def task_booking_reserve():
    """Book a room."""

    def ground_truth(sim_url):
        try:
            r = http.get(f"{sim_url}/api/bookings", timeout=5)
            if r.status_code == 200:
                data = r.json()
                bookings = data.get("bookings", data) if isinstance(data, dict) else data
                return len(bookings) > 0
        except Exception:
            pass
        return False

    return AgentTask(
        id="booking-reserve",
        site="booking",
        goal=(
            "Book a room. "
            "1. Login with email alice@example.com and password password123. "
            "2. Search for available rooms. "
            "3. Book the cheapest room for tonight."
        ),
        contract_path=_contract_path("booking"),
        simulation_dir=_sim_path("booking"),
        simulation_port=8105,
        max_steps=12,
        ground_truth=ground_truth,
        category="transaction",
        description="Complete booking: login → search → reserve",
    )


# ══════════════════════════════════════════════
# LIBRARY TASKS
# ══════════════════════════════════════════════

def task_library_browse():
    """Browse the library catalog."""

    def ground_truth(sim_url):
        try:
            r = http.get(f"{sim_url}/api/documents", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    return AgentTask(
        id="library-browse",
        site="library",
        goal="Browse the library. Search the catalog and view at least one document's details.",
        contract_path=_contract_path("library"),
        simulation_dir=_sim_path("library"),
        simulation_port=8106,
        max_steps=8,
        ground_truth=ground_truth,
        category="navigation",
        description="Browse library catalog",
    )


def task_library_request():
    """Submit a document request."""

    def ground_truth(sim_url):
        try:
            r = http.get(f"{sim_url}/api/requests", timeout=5)
            if r.status_code == 200:
                data = r.json()
                reqs = data.get("requests", data) if isinstance(data, dict) else data
                return len(reqs) > 0
        except Exception:
            pass
        return False

    return AgentTask(
        id="library-request-doc",
        site="library",
        goal=(
            "Request a document from the library. "
            "1. Login with email citizen@example.com and password password123. "
            "2. Search for any available document. "
            "3. Submit a request for it."
        ),
        contract_path=_contract_path("library"),
        simulation_dir=_sim_path("library"),
        simulation_port=8107,
        max_steps=12,
        ground_truth=ground_truth,
        category="transaction",
        description="Submit document request: login → search → request",
    )


# ══════════════════════════════════════════════
# TASK REGISTRY
# ══════════════════════════════════════════════

TASK_REGISTRY = {
    # Shopping
    "shopping-browse": task_shopping_browse,
    "shopping-search-cart": task_shopping_search_and_cart,
    "shopping-full-purchase": task_shopping_full_purchase,

    # Booking
    "booking-search": task_booking_search,
    "booking-reserve": task_booking_reserve,

    # Library
    "library-browse": task_library_browse,
    "library-request-doc": task_library_request,
}


def get_task(task_id: str) -> AgentTask:
    """Get a task by ID."""
    factory = TASK_REGISTRY.get(task_id)
    return factory() if factory else None


def get_all_tasks() -> list[AgentTask]:
    """Get all registered tasks."""
    return [factory() for factory in TASK_REGISTRY.values()]


def get_tasks_by_category(category: str) -> list[AgentTask]:
    """Get tasks by category."""
    return [t for t in get_all_tasks() if t.category == category]
