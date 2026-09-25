"""
Subway Gov Service Contract
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


def build_library_contract() -> SubwayContract:

    # ── Screen: Auth Gate (entry point) ──
    auth_screen = ScreenDefinition(
        id="auth_gate",
        name="Authentication",
        description="Login or register to access government services. "
                    "Document browsing is available without login. "
                    "Submitting requests requires authentication. "
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
                transitions_to="document_search",
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
                transitions_to="document_search",
                api_endpoint="/api/auth/register",
                api_method="POST",
            ),
            ActionDefinition(
                id="browse_without_login",
                name="Browse without login",
                description="Browse documents without logging in. Cannot submit service requests.",
                transitions_to="document_search",
            ),
        ],
    )

    # ── Screen: Document Search ──
    search_screen = ScreenDefinition(
        id="document_search",
        name="Document search",
        description="Search government documents, permits, certificates, forms, and guides.",
        data_fields=[
            DataField(name="documents", type="list", description="List of matching documents"),
            DataField(name="total", type="int", description="Total results"),
        ],
        actions=[
            ActionDefinition(
                id="search_documents",
                name="Search documents",
                description="Search the document catalog by keyword, category, or department.",
                parameters=[
                    ActionParameter(name="q", type="string", required=False, description="Search keyword"),
                    ActionParameter(name="category", type="enum", required=False,
                                    description="Document category",
                                    enum_values=["permits", "certificates", "forms", "guides", "regulations"]),
                    ActionParameter(name="department", type="enum", required=False,
                                    description="Government department",
                                    enum_values=["building_department", "health_department",
                                                 "business_licensing", "vital_records", "transportation"]),
                    ActionParameter(name="has_fee", type="bool", required=False,
                                    description="Filter by whether document has a fee"),
                ],
                transitions_to="document_search",
                api_endpoint="/api/documents",
                api_method="GET",
            ),
            ActionDefinition(
                id="view_document",
                name="View document details",
                description="View full details of a document including requirements and fees.",
                parameters=[
                    ActionParameter(name="doc_id", type="string", required=True,
                                    description="Document ID to view"),
                ],
                transitions_to="document_detail",
                api_endpoint="/api/documents/{doc_id}",
                api_method="GET",
            ),
            ActionDefinition(
                id="view_departments",
                name="View departments",
                description="List all departments with their services and queue status.",
                transitions_to="department_list",
                api_endpoint="/api/departments",
                api_method="GET",
            ),
            ActionDefinition(
                id="track_request",
                name="Track a request",
                description="Check the status of an existing service request by ID.",
                parameters=[
                    ActionParameter(name="req_id", type="string", required=True,
                                    description="Request ID to track"),
                ],
                transitions_to="request_status",
                api_endpoint="/api/requests/{req_id}",
                api_method="GET",
            ),
        ]
    )

    # ── Screen: Document Detail ──
    doc_detail_screen = ScreenDefinition(
        id="document_detail",
        name="Document detail",
        description="Full document info with requirements, fees, and processing times.",
        parameters=["doc_id"],
        data_fields=[
            DataField(name="title", type="string", description="Document title"),
            DataField(name="category", type="string", description="Category"),
            DataField(name="department", type="string", description="Responsible department"),
            DataField(name="content_summary", type="string", description="Detailed summary"),
            DataField(name="requirements", type="list", description="List of requirements"),
            DataField(name="fee", type="float", description="Fee amount (0 if free)"),
            DataField(name="processing_days", type="int", description="Processing time in business days"),
        ],
        actions=[
            ActionDefinition(
                id="submit_request",
                name="Submit a service request",
                description="Start a request related to this document (permit application, certificate request, etc.).",
                permission=ActionPermission.REQUIRES_CONFIRMATION,
                parameters=[
                    ActionParameter(name="request_type", type="enum", required=True,
                                    description="Type of request",
                                    enum_values=["permit_application", "certificate_request",
                                                 "form_submission", "information_request"]),
                    ActionParameter(name="document_id", type="string", required=False,
                                    description="Related document ID"),
                    ActionParameter(name="department", type="string", required=True,
                                    description="Department to submit to"),
                    ActionParameter(name="applicant_name", type="string", required=True,
                                    description="Full name of applicant"),
                    ActionParameter(name="applicant_email", type="string", required=True,
                                    description="Email address"),
                    ActionParameter(name="applicant_phone", type="string", required=False,
                                    description="Phone number"),
                    ActionParameter(name="details", type="string", required=False,
                                    description="Additional details about the request"),
                ],
                transitions_to="request_status",
                api_endpoint="/api/requests",
                api_method="POST",
            ),
            ActionDefinition(
                id="back_to_search",
                name="Back to search",
                description="Return to document search.",
                transitions_to="document_search",
            ),
        ],
        parent="document_search",
    )

    # ── Screen: Department List ──
    dept_list_screen = ScreenDefinition(
        id="department_list",
        name="Department list",
        description="All government departments with document counts and queue status.",
        data_fields=[
            DataField(name="departments", type="list",
                      description="Departments with name, document count, pending requests, queue length"),
        ],
        actions=[
            ActionDefinition(
                id="search_by_department",
                name="Search documents by department",
                description="View all documents from a specific department.",
                parameters=[
                    ActionParameter(name="department", type="enum", required=True,
                                    description="Department to filter by",
                                    enum_values=["building_department", "health_department",
                                                 "business_licensing", "vital_records", "transportation"]),
                ],
                transitions_to="document_search",
                api_endpoint="/api/documents",
                api_method="GET",
            ),
            ActionDefinition(
                id="back_to_search_from_depts",
                name="Back to search",
                description="Return to document search.",
                transitions_to="document_search",
            ),
        ],
    )

    # ── Screen: Request Status ──
    request_status_screen = ScreenDefinition(
        id="request_status",
        name="Request status",
        description="Status and details of a service request.",
        data_fields=[
            DataField(name="request_id", type="string", description="Request ID"),
            DataField(name="status", type="string", description="Current status"),
            DataField(name="queue_position", type="int", description="Position in processing queue"),
            DataField(name="estimated_completion", type="string", description="Estimated completion date"),
            DataField(name="fee_paid", type="float", description="Fee amount"),
            DataField(name="message", type="string", description="Status message"),
        ],
        actions=[
            ActionDefinition(
                id="check_requirements",
                name="Check requirements",
                description="View the requirements checklist for this request.",
                parameters=[
                    ActionParameter(name="req_id", type="string", required=True,
                                    description="Request ID"),
                ],
                transitions_to="request_status",
                api_endpoint="/api/requests/{req_id}/requirements",
                api_method="GET",
            ),
            ActionDefinition(
                id="new_search",
                name="New search",
                description="Start a new document search.",
                transitions_to="document_search",
            ),
        ],
    )

    # ── Assemble Contract ──
    contract = SubwayContract(
        contract_id="subway_gov_v2_auth",
        version="0.2.0",
        site_name="SubwayGov Document Library & Services (with Auth)",
        site_url="http://localhost:8004",
        description="Government document library and service portal with authentication. "
                    "Document browsing is public. Submitting requests requires login. "
                    "Test accounts: alice@example.com/password123, bob@example.com/securepass",
        tier=ContractTier.STANDARD,

        screens=[auth_screen, search_screen, doc_detail_screen, dept_list_screen, request_status_screen],
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
                "applicant_email": DataRetention.NONE,
                "applicant_phone": DataRetention.NONE,
                "applicant_address": DataRetention.NONE,
            },
            allow_aggregation=False,
            allow_storage=False,
        ),

        prohibited_actions=["bulk_scrape", "access_admin", "modify_records"],
        required_confirmations=["submit_request"],

        action_trust_requirements=[
            ActionTrustRequirement(action_id="submit_request", min_trust_level=AgentTrust.VERIFIED),
        ],
        default_trust_for_actions=AgentTrust.IDENTIFIED,

        require_identification=True,
        allowed_purposes=["document_search", "permit_application", "research", "information", "purchase"],
        blocked_providers=[],
        log_all_actions=True,
        log_data_access=True,
    )

    return contract


if __name__ == "__main__":
    contract = build_library_contract()
    output = str(Path(__file__).parent / "contract.json")
    with open(output, "w") as f:
        json.dump(contract.model_dump(mode="json"), f, indent=2)
    print(f"Gov service contract exported to {output}")
    print(f"  Screens: {len(contract.screens)}")
    print(f"  Actions: {sum(len(s.actions) for s in contract.screens)}")
