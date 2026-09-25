"""
Subway Library / Gov Service Simulation - Data Models & In-Memory Store

A public document library + service request portal:
- Document catalog with categories (permits, certificates, forms, guides)
- Document search and detail viewing
- Service requests (apply for permit, request certificate, submit form)
- Request tracking with status lifecycle: submitted → under_review → approved/rejected
- Queue position and estimated wait times
"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
import uuid
from datetime import datetime, timedelta
import random


# ── Enums ──

class DocumentCategory(str, Enum):
    PERMITS = "permits"
    CERTIFICATES = "certificates"
    FORMS = "forms"
    GUIDES = "guides"
    REGULATIONS = "regulations"


class Department(str, Enum):
    BUILDING = "building_department"
    HEALTH = "health_department"
    BUSINESS = "business_licensing"
    VITAL_RECORDS = "vital_records"
    TRANSPORTATION = "transportation"


class RequestStatus(str, Enum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    ADDITIONAL_INFO_NEEDED = "additional_info_needed"
    APPROVED = "approved"
    REJECTED = "rejected"


class RequestType(str, Enum):
    PERMIT_APPLICATION = "permit_application"
    CERTIFICATE_REQUEST = "certificate_request"
    FORM_SUBMISSION = "form_submission"
    INFORMATION_REQUEST = "information_request"


# ── Models ──

class Document(BaseModel):
    id: str
    title: str
    category: DocumentCategory
    department: Department
    description: str
    content_summary: str
    requirements: list[str] = []
    fee: Optional[float] = None
    processing_days: Optional[int] = None
    last_updated: str = ""
    download_url: str = ""


class ApplicantInfo(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    id_number: Optional[str] = None


class ServiceRequest(BaseModel):
    id: str
    request_type: RequestType
    document_id: Optional[str] = None
    department: Department
    applicant: ApplicantInfo
    details: str = ""
    status: RequestStatus = RequestStatus.SUBMITTED
    queue_position: Optional[int] = None
    estimated_completion: Optional[str] = None
    fee_paid: float = 0.0
    notes: list[str] = []
    created_at: str = ""
    updated_at: str = ""


# ── Request/Response Schemas ──

class DocumentSearchResponse(BaseModel):
    documents: list[Document]
    total: int


class ServiceRequestCreate(BaseModel):
    request_type: RequestType
    document_id: Optional[str] = None
    department: str
    applicant_name: str
    applicant_email: str
    applicant_phone: Optional[str] = None
    applicant_address: Optional[str] = None
    details: Optional[str] = None


class ServiceRequestResponse(BaseModel):
    request: ServiceRequest
    message: str = ""


# ── In-Memory Database ──

DOCUMENTS: dict[str, Document] = {}
REQUESTS: dict[str, ServiceRequest] = {}
QUEUE_COUNTER: dict[str, int] = {}


def seed_data():
    """Populate with sample documents and services."""
    docs_data = [
        # Permits
        ("Building Permit Application", DocumentCategory.PERMITS, Department.BUILDING,
         "Apply for a new construction or renovation building permit.",
         "Required for any structural changes, new construction, or major renovations. "
         "Includes residential and commercial projects.",
         ["Completed application form", "Site plan/blueprints", "Proof of property ownership",
          "Contractor license (if applicable)", "Environmental impact assessment (for large projects)"],
         150.00, 15),

        ("Food Service Permit", DocumentCategory.PERMITS, Department.HEALTH,
         "Permit required to operate a food service establishment.",
         "Covers restaurants, food trucks, catering services, and temporary food events. "
         "Requires health inspection prior to approval.",
         ["Completed application", "Floor plan of kitchen/service area", "Menu",
          "Food safety certification", "Health inspection appointment"],
         200.00, 20),

        ("Business License", DocumentCategory.PERMITS, Department.BUSINESS,
         "General business operating license for the city.",
         "Required for all businesses operating within city limits. Renewed annually. "
         "Different fee tiers based on business size and type.",
         ["Completed application", "Proof of business address", "Tax ID number",
          "Zoning compliance letter", "Insurance certificate"],
         75.00, 10),

        ("Street Event Permit", DocumentCategory.PERMITS, Department.TRANSPORTATION,
         "Permit for organizing events on public streets or sidewalks.",
         "Required for parades, street fairs, marathons, and any event that temporarily "
         "closes or restricts public roadways.",
         ["Event plan with route/area map", "Traffic management plan", "Insurance certificate",
          "Security plan (for events over 500 people)", "Noise waiver (if applicable)"],
         300.00, 30),

        # Certificates
        ("Birth Certificate", DocumentCategory.CERTIFICATES, Department.VITAL_RECORDS,
         "Request a certified copy of a birth certificate.",
         "Available for births recorded in the city. Standard and expedited processing available. "
         "Acceptable as legal identification document.",
         ["Valid government ID", "Proof of relationship (if requesting for another person)",
          "Completed request form"],
         25.00, 5),

        ("Death Certificate", DocumentCategory.CERTIFICATES, Department.VITAL_RECORDS,
         "Request a certified copy of a death certificate.",
         "Available for deaths recorded in the city. Required for estate settlement, "
         "insurance claims, and legal proceedings.",
         ["Valid government ID", "Proof of relationship or legal authority",
          "Completed request form"],
         25.00, 5),

        ("Marriage Certificate", DocumentCategory.CERTIFICATES, Department.VITAL_RECORDS,
         "Request a certified copy of a marriage certificate.",
         "Available for marriages performed in the city. Used for name changes, "
         "insurance enrollment, and immigration purposes.",
         ["Valid government ID for both parties", "Marriage date and location",
          "Completed request form"],
         30.00, 5),

        # Forms
        ("Change of Address Form", DocumentCategory.FORMS, Department.VITAL_RECORDS,
         "Update your address on city records.",
         "Updates your address across all city departments simultaneously. "
         "Important for voter registration, tax records, and service delivery.",
         ["New address proof (utility bill or lease)", "Valid government ID"],
         0.00, 3),

        ("Property Tax Appeal Form", DocumentCategory.FORMS, Department.BUSINESS,
         "Appeal your property tax assessment.",
         "File within 60 days of assessment notice. Requires comparable property data "
         "or independent appraisal to support lower valuation.",
         ["Assessment notice", "Comparable property sales data", "Independent appraisal (optional)",
          "Photos of property condition (if relevant)"],
         0.00, 45),

        ("Noise Complaint Form", DocumentCategory.FORMS, Department.HEALTH,
         "File a noise complaint against a property or business.",
         "For ongoing noise violations. Single incidents should be reported to police. "
         "Triggers investigation within 5 business days.",
         ["Your contact information", "Location of noise source", "Description of noise",
          "Dates and times of occurrences"],
         0.00, 5),

        # Guides
        ("New Resident Guide", DocumentCategory.GUIDES, Department.VITAL_RECORDS,
         "Complete guide for new city residents.",
         "Covers registration, utilities setup, school enrollment, public transit, "
         "healthcare providers, and community resources. Updated quarterly.",
         [], None, None),

        ("Small Business Startup Guide", DocumentCategory.GUIDES, Department.BUSINESS,
         "Step-by-step guide to starting a business in the city.",
         "Covers business structure selection, licensing requirements, tax registration, "
         "zoning compliance, and available grants/incentives.",
         [], None, None),

        # Regulations
        ("Zoning Regulations", DocumentCategory.REGULATIONS, Department.BUILDING,
         "Complete zoning code for the city.",
         "Defines permitted land uses, building heights, setbacks, parking requirements, "
         "and special district rules for all zones.",
         [], None, None),

        ("Health Code", DocumentCategory.REGULATIONS, Department.HEALTH,
         "Public health regulations and standards.",
         "Covers food safety, water quality, waste management, pest control, "
         "and occupational health requirements.",
         [], None, None),

        ("Parking Regulations", DocumentCategory.REGULATIONS, Department.TRANSPORTATION,
         "Complete parking rules and permit information.",
         "Covers street parking zones, residential permits, commercial loading zones, "
         "meter rates, and violation penalties.",
         [], None, None),
    ]

    for i, (title, cat, dept, desc, summary, reqs, fee, days) in enumerate(docs_data):
        did = f"doc_{i+1:03d}"
        DOCUMENTS[did] = Document(
            id=did, title=title, category=cat, department=dept,
            description=desc, content_summary=summary,
            requirements=reqs, fee=fee, processing_days=days,
            last_updated="2026-03-15",
            download_url=f"/documents/{did}.pdf",
        )

    # Initialize queue counters per department
    for dept in Department:
        QUEUE_COUNTER[dept.value] = random.randint(5, 25)

    # Pre-create some sample requests for status tracking demos
    sample_requests = [
        ("req_sample_001", RequestType.PERMIT_APPLICATION, "doc_001", Department.BUILDING,
         ApplicantInfo(name="Maria Garcia", email="maria@example.com"),
         "Residential renovation, 2nd floor addition", RequestStatus.UNDER_REVIEW, 8),
        ("req_sample_002", RequestType.CERTIFICATE_REQUEST, "doc_005", Department.VITAL_RECORDS,
         ApplicantInfo(name="James Chen", email="james@example.com"),
         "Birth certificate for passport application", RequestStatus.APPROVED, 0),
    ]

    for rid, rtype, doc_id, dept, applicant, details, status, queue in sample_requests:
        REQUESTS[rid] = ServiceRequest(
            id=rid, request_type=rtype, document_id=doc_id,
            department=dept, applicant=applicant, details=details,
            status=status, queue_position=queue if status == RequestStatus.UNDER_REVIEW else None,
            estimated_completion=(datetime.utcnow() + timedelta(days=queue)).isoformat() if queue else None,
            created_at=(datetime.utcnow() - timedelta(days=3)).isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )


def create_request(req_type: RequestType, doc_id: Optional[str],
                   department: Department, applicant: ApplicantInfo,
                   details: str = "") -> ServiceRequest:
    """Create a new service request."""
    rid = f"req_{uuid.uuid4().hex[:8]}"

    # Assign queue position
    QUEUE_COUNTER[department.value] = QUEUE_COUNTER.get(department.value, 0) + 1
    queue_pos = QUEUE_COUNTER[department.value]

    # Estimate completion based on document processing days or default
    doc = DOCUMENTS.get(doc_id) if doc_id else None
    est_days = doc.processing_days if doc and doc.processing_days else 10
    est_completion = (datetime.utcnow() + timedelta(days=est_days)).isoformat()

    fee = doc.fee if doc and doc.fee else 0.0

    request = ServiceRequest(
        id=rid, request_type=req_type, document_id=doc_id,
        department=department, applicant=applicant, details=details,
        status=RequestStatus.SUBMITTED,
        queue_position=queue_pos,
        estimated_completion=est_completion,
        fee_paid=fee,
        notes=[f"Request submitted. Queue position: #{queue_pos}"],
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat(),
    )
    REQUESTS[rid] = request
    return request
