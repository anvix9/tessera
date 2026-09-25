"""
Subway Library / Gov Service Simulation - FastAPI Application (Level 2: Auth & Sessions)

Public endpoints (no auth):
  GET  /api/documents              - Search documents
  GET  /api/documents/{id}         - Document detail
  GET  /api/departments            - List departments
  POST /api/auth/register          - Create account
  POST /api/auth/login             - Login

Protected endpoints (require Authorization: Bearer <token>):
  POST /api/requests               - Submit a service request
  GET  /api/requests/{id}          - Check request status
  GET  /api/requests/{id}/requirements - Get requirements
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.responses import HTMLResponse
from typing import Optional

from models import (
    DOCUMENTS, REQUESTS, QUEUE_COUNTER,
    seed_data, create_request,
    Document, DocumentCategory, Department, RequestType,
    RequestStatus, ApplicantInfo,
    DocumentSearchResponse, ServiceRequestCreate, ServiceRequestResponse,
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
    title="Subway Gov Service Simulation",
    description="Simulated government service portal with authentication (Level 2)",
    version="0.2.0",
    lifespan=lifespan,
)


# ── Auth Dependency ──

def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
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


# ── Document Endpoints ──

@app.get("/api/documents", response_model=DocumentSearchResponse)
def search_documents(
    q: Optional[str] = Query(None, description="Search keyword"),
    category: Optional[DocumentCategory] = Query(None, description="Filter by category"),
    department: Optional[Department] = Query(None, description="Filter by department"),
    has_fee: Optional[bool] = Query(None, description="Filter by whether document has a fee"),
):
    """Search the document catalog."""
    results = list(DOCUMENTS.values())

    # Filter by category
    if category:
        results = [d for d in results if d.category == category]

    # Filter by department
    if department:
        results = [d for d in results if d.department == department]

    # Filter by fee
    if has_fee is not None:
        if has_fee:
            results = [d for d in results if d.fee and d.fee > 0]
        else:
            results = [d for d in results if not d.fee or d.fee == 0]

    # Search by keyword
    if q:
        q_lower = q.lower().strip()
        if q_lower:
            results = [d for d in results if (
                q_lower in d.title.lower()
                or q_lower in d.description.lower()
                or q_lower in d.content_summary.lower()
                or q_lower in d.category.value.lower()
                or q_lower in d.department.value.lower()
                or any(word in d.title.lower() or word in d.description.lower()
                       for word in q_lower.split() if len(word) > 2)
            )]

    return DocumentSearchResponse(documents=results, total=len(results))


@app.get("/api/documents/{doc_id}", response_model=Document)
def get_document(doc_id: str):
    """Get full document details including requirements and fees."""
    if doc_id not in DOCUMENTS:
        raise HTTPException(status_code=404, detail="Document not found")
    return DOCUMENTS[doc_id]


# ── Department Endpoints ──

@app.get("/api/departments")
def list_departments():
    """List all departments with their document and queue counts."""
    depts = []
    for dept in Department:
        docs = [d for d in DOCUMENTS.values() if d.department == dept]
        pending = len([r for r in REQUESTS.values()
                       if r.department == dept
                       and r.status in (RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW)])
        depts.append({
            "id": dept.value,
            "name": dept.value.replace("_", " ").title(),
            "document_count": len(docs),
            "pending_requests": pending,
            "current_queue": QUEUE_COUNTER.get(dept.value, 0),
        })
    return {"departments": depts}


# ── Service Request Endpoints (Protected) ──

@app.post("/api/requests", response_model=ServiceRequestResponse)
def submit_request(req: ServiceRequestCreate, user: User = Depends(get_current_user)):
    """Submit a new service request. Requires login."""
    # Validate department
    try:
        dept = Department(req.department)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid department. Valid: {[d.value for d in Department]}"
        )

    # Validate document if provided
    if req.document_id and req.document_id not in DOCUMENTS:
        raise HTTPException(status_code=404, detail="Document not found")

    # Validate applicant
    if not req.applicant_name or not req.applicant_email:
        raise HTTPException(status_code=400, detail="Applicant name and email are required")

    applicant = ApplicantInfo(
        name=req.applicant_name,
        email=req.applicant_email,
        phone=req.applicant_phone,
        address=req.applicant_address,
    )

    service_req = create_request(
        req_type=req.request_type,
        doc_id=req.document_id,
        department=dept,
        applicant=applicant,
        details=req.details or "",
    )

    doc = DOCUMENTS.get(req.document_id) if req.document_id else None
    fee_msg = f" Fee: ${service_req.fee_paid}." if service_req.fee_paid > 0 else " No fee."
    return ServiceRequestResponse(
        request=service_req,
        message=f"Request {service_req.id} submitted successfully. "
                f"Queue position: #{service_req.queue_position}. "
                f"Estimated completion: {service_req.estimated_completion[:10]}.{fee_msg}"
    )


@app.get("/api/requests/{req_id}", response_model=ServiceRequestResponse)
def get_request(req_id: str, user: User = Depends(get_current_user)):
    """Check request status and queue position. Requires login."""
    if req_id not in REQUESTS:
        raise HTTPException(status_code=404, detail="Request not found")
    req = REQUESTS[req_id]
    status_msg = {
        RequestStatus.SUBMITTED: "Your request has been received and is waiting for review.",
        RequestStatus.UNDER_REVIEW: f"Your request is being reviewed. Queue position: #{req.queue_position}.",
        RequestStatus.ADDITIONAL_INFO_NEEDED: "Additional information is required. Check notes for details.",
        RequestStatus.APPROVED: "Your request has been approved!",
        RequestStatus.REJECTED: "Your request has been rejected. Check notes for reason.",
    }
    return ServiceRequestResponse(
        request=req,
        message=status_msg.get(req.status, f"Status: {req.status.value}")
    )


@app.get("/api/requests/{req_id}/requirements")
def get_request_requirements(req_id: str, user: User = Depends(get_current_user)):
    """Get the requirements checklist for a pending request. Requires login."""
    if req_id not in REQUESTS:
        raise HTTPException(status_code=404, detail="Request not found")
    req = REQUESTS[req_id]

    doc = DOCUMENTS.get(req.document_id) if req.document_id else None
    requirements = doc.requirements if doc else []

    return {
        "request_id": req.id,
        "status": req.status.value,
        "requirements": requirements,
        "fee": doc.fee if doc else 0,
        "processing_days": doc.processing_days if doc else None,
        "message": f"{len(requirements)} requirements for this request."
                   + (f" Fee: ${doc.fee}." if doc and doc.fee else "")
    }


# ── HTML Frontend ──

@app.get("/", response_class=HTMLResponse)
def homepage():
    return get_frontend_html()


def get_frontend_html():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SubwayGov - Document Library & Services</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }
  header { background: #1a3a2e; color: white; padding: 16px 24px; }
  header h1 { font-size: 22px; } header h1 span { color: #4caf50; }
  .container { max-width: 1100px; margin: 0 auto; padding: 24px; }
  .tabs { display: flex; gap: 0; margin-bottom: 24px; }
  .tab { padding: 10px 24px; background: white; border: 1px solid #ddd; cursor: pointer; font-size: 14px; font-weight: 500; }
  .tab:first-child { border-radius: 8px 0 0 8px; }
  .tab:last-child { border-radius: 0 8px 8px 0; }
  .tab.active { background: #1a3a2e; color: white; border-color: #1a3a2e; }
  .search-bar { display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
  .search-bar input, .search-bar select { padding: 10px 14px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; }
  .search-bar input { flex: 1; min-width: 200px; }
  .search-bar button { padding: 10px 20px; background: #4caf50; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }
  .docs { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
  .doc-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-left: 4px solid #4caf50; }
  .doc-card h3 { font-size: 16px; margin-bottom: 4px; }
  .doc-card .dept { color: #4caf50; font-size: 12px; text-transform: uppercase; font-weight: 600; }
  .doc-card .cat { background: #e8f5e9; color: #2e7d32; padding: 2px 8px; border-radius: 4px; font-size: 11px; display: inline-block; margin: 4px 0; }
  .doc-card .meta { font-size: 13px; color: #777; margin-top: 6px; }
  .doc-card .fee { font-weight: 700; color: #1a3a2e; }
  .detail-btn { display: inline-block; margin-top: 10px; padding: 8px 16px; background: #1a3a2e; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
  .detail-btn:hover { background: #2a5a4e; }
  .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 100; justify-content: center; align-items: center; }
  .modal-overlay.active { display: flex; }
  .modal { background: white; border-radius: 16px; padding: 28px; max-width: 600px; width: 90%; max-height: 85vh; overflow-y: auto; }
  .modal h2 { margin-bottom: 16px; }
  .modal-close { float: right; background: none; border: none; font-size: 24px; cursor: pointer; color: #999; }
  .req-list { list-style: none; padding: 0; } .req-list li { padding: 6px 0; border-bottom: 1px solid #f0f0f0; font-size: 14px; }
  .req-list li:before { content: "\\2713  "; color: #4caf50; font-weight: bold; }
  .form-group { margin: 10px 0; }
  .form-group label { display: block; font-size: 13px; font-weight: 500; color: #555; margin-bottom: 4px; }
  .form-group input, .form-group textarea, .form-group select { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; }
  .form-group textarea { height: 80px; resize: vertical; }
  .submit-btn { width: 100%; margin-top: 16px; padding: 14px; background: #4caf50; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; }
  .status-card { background: white; border-radius: 12px; padding: 24px; margin-top: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
  .status-badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }
  .status-submitted { background: #fff3e0; color: #e65100; }
  .status-under_review { background: #e3f2fd; color: #1565c0; }
  .status-approved { background: #e8f5e9; color: #2e7d32; }
  .status-rejected { background: #ffebee; color: #c62828; }
  .empty { text-align: center; color: #999; padding: 40px; }
  #track-section { margin-top: 24px; }
  .track-bar { display: flex; gap: 8px; }
  .track-bar input { flex: 1; padding: 10px 14px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; }
  .track-bar button { padding: 10px 20px; background: #1a3a2e; color: white; border: none; border-radius: 8px; cursor: pointer; }
</style>
</head>
<body>
<header><h1><span>Subway</span>Gov</h1></header>
<div class="container">
  <div class="tabs">
    <div class="tab active" onclick="switchTab('documents')">Documents</div>
    <div class="tab" onclick="switchTab('request')">Submit Request</div>
    <div class="tab" onclick="switchTab('track')">Track Request</div>
  </div>

  <!-- Documents Tab -->
  <div id="documents-tab">
    <div class="search-bar">
      <input type="text" id="search-input" placeholder="Search documents..." onkeydown="if(event.key==='Enter')searchDocs()">
      <select id="cat-filter">
        <option value="">All Categories</option>
        <option value="permits">Permits</option>
        <option value="certificates">Certificates</option>
        <option value="forms">Forms</option>
        <option value="guides">Guides</option>
        <option value="regulations">Regulations</option>
      </select>
      <select id="dept-filter">
        <option value="">All Departments</option>
        <option value="building_department">Building</option>
        <option value="health_department">Health</option>
        <option value="business_licensing">Business</option>
        <option value="vital_records">Vital Records</option>
        <option value="transportation">Transportation</option>
      </select>
      <button onclick="searchDocs()">Search</button>
    </div>
    <div class="docs" id="docs-grid"></div>
  </div>

  <!-- Submit Request Tab -->
  <div id="request-tab" style="display:none">
    <div class="status-card">
      <h2>Submit a Service Request</h2>
      <div class="form-group"><label>Request Type</label>
        <select id="req-type">
          <option value="permit_application">Permit Application</option>
          <option value="certificate_request">Certificate Request</option>
          <option value="form_submission">Form Submission</option>
          <option value="information_request">Information Request</option>
        </select>
      </div>
      <div class="form-group"><label>Department</label>
        <select id="req-dept">
          <option value="building_department">Building Department</option>
          <option value="health_department">Health Department</option>
          <option value="business_licensing">Business Licensing</option>
          <option value="vital_records">Vital Records</option>
          <option value="transportation">Transportation</option>
        </select>
      </div>
      <div class="form-group"><label>Related Document ID (optional)</label><input id="req-doc" placeholder="e.g., doc_001"></div>
      <div class="form-group"><label>Full Name</label><input id="req-name" placeholder="Jane Doe"></div>
      <div class="form-group"><label>Email</label><input id="req-email" placeholder="jane@example.com"></div>
      <div class="form-group"><label>Phone (optional)</label><input id="req-phone" placeholder="+1 555 123 4567"></div>
      <div class="form-group"><label>Details</label><textarea id="req-details" placeholder="Describe your request..."></textarea></div>
      <button class="submit-btn" onclick="submitRequest()">Submit Request</button>
      <div id="req-result" style="margin-top:16px"></div>
    </div>
  </div>

  <!-- Track Request Tab -->
  <div id="track-tab" style="display:none">
    <div class="track-bar">
      <input type="text" id="track-id" placeholder="Enter request ID (e.g., req_sample_001)">
      <button onclick="trackRequest()">Track</button>
    </div>
    <div id="track-result"></div>
  </div>
</div>

<!-- Document Detail Modal -->
<div class="modal-overlay" id="doc-modal">
  <div class="modal">
    <button class="modal-close" onclick="closeModal('doc-modal')">&times;</button>
    <div id="doc-detail"></div>
  </div>
</div>

<script>
function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('[id$="-tab"]').forEach(t => t.style.display = 'none');
  event.target.classList.add('active');
  document.getElementById(tab + '-tab').style.display = 'block';
}

async function searchDocs() {
  const q = document.getElementById('search-input').value;
  const cat = document.getElementById('cat-filter').value;
  const dept = document.getElementById('dept-filter').value;
  let url = '/api/documents?';
  if (q) url += `q=${encodeURIComponent(q)}&`;
  if (cat) url += `category=${cat}&`;
  if (dept) url += `department=${dept}&`;
  const r = await fetch(url);
  const data = await r.json();
  renderDocs(data.documents);
}

function renderDocs(docs) {
  const grid = document.getElementById('docs-grid');
  if (!docs.length) { grid.innerHTML = '<div class="empty">No documents found</div>'; return; }
  grid.innerHTML = docs.map(d => {
    const fee = d.fee ? `$${d.fee}` : 'Free';
    const days = d.processing_days ? `${d.processing_days} days` : '';
    return `<div class="doc-card">
      <div class="dept">${d.department.replace(/_/g,' ')}</div>
      <h3>${d.title}</h3>
      <span class="cat">${d.category}</span>
      <p class="meta">${d.description}</p>
      <div class="meta" style="margin-top:8px">
        <span class="fee">${fee}</span> ${days ? ' · ' + days + ' processing' : ''}
      </div>
      <button class="detail-btn" onclick="viewDoc('${d.id}')">View Details</button>
    </div>`;
  }).join('');
}

async function viewDoc(docId) {
  const r = await fetch(`/api/documents/${docId}`);
  const d = await r.json();
  const fee = d.fee ? `$${d.fee}` : 'Free';
  document.getElementById('doc-detail').innerHTML = `
    <div class="dept">${d.department.replace(/_/g,' ')}</div>
    <h2>${d.title}</h2>
    <span class="cat">${d.category}</span>
    <p style="margin:12px 0">${d.content_summary}</p>
    ${d.requirements.length ? `<h3 style="margin-top:16px">Requirements</h3>
      <ul class="req-list">${d.requirements.map(r => `<li>${r}</li>`).join('')}</ul>` : ''}
    <div style="margin-top:16px;padding:12px;background:#f5f5f5;border-radius:8px">
      <strong>Fee:</strong> ${fee} · 
      ${d.processing_days ? `<strong>Processing:</strong> ${d.processing_days} business days` : 'No processing time'}
    </div>
  `;
  document.getElementById('doc-modal').classList.add('active');
}

async function submitRequest() {
  const r = await fetch('/api/requests', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      request_type: document.getElementById('req-type').value,
      department: document.getElementById('req-dept').value,
      document_id: document.getElementById('req-doc').value || null,
      applicant_name: document.getElementById('req-name').value,
      applicant_email: document.getElementById('req-email').value,
      applicant_phone: document.getElementById('req-phone').value || null,
      details: document.getElementById('req-details').value || null,
    })
  });
  if (!r.ok) { const err = await r.json(); alert(err.detail); return; }
  const data = await r.json();
  document.getElementById('req-result').innerHTML = `
    <div class="status-card" style="background:#e8f5e9">
      <h3 style="color:#2e7d32">Request Submitted!</h3>
      <p>${data.message}</p>
      <p style="margin-top:8px"><strong>Request ID:</strong> ${data.request.id} (save this to track your request)</p>
    </div>`;
}

async function trackRequest() {
  const id = document.getElementById('track-id').value.trim();
  if (!id) { alert('Enter a request ID'); return; }
  const r = await fetch(`/api/requests/${id}`);
  if (!r.ok) { document.getElementById('track-result').innerHTML = '<div class="status-card"><p>Request not found.</p></div>'; return; }
  const data = await r.json();
  const req = data.request;
  const statusClass = `status-${req.status}`;
  document.getElementById('track-result').innerHTML = `
    <div class="status-card">
      <h3>Request ${req.id}</h3>
      <span class="status-badge ${statusClass}">${req.status.replace(/_/g,' ').toUpperCase()}</span>
      <p style="margin-top:12px">${data.message}</p>
      <div style="margin-top:12px;font-size:14px;color:#555">
        <p><strong>Type:</strong> ${req.request_type.replace(/_/g,' ')}</p>
        <p><strong>Department:</strong> ${req.department.replace(/_/g,' ')}</p>
        ${req.queue_position ? `<p><strong>Queue Position:</strong> #${req.queue_position}</p>` : ''}
        ${req.estimated_completion ? `<p><strong>Est. Completion:</strong> ${req.estimated_completion.slice(0,10)}</p>` : ''}
        ${req.fee_paid > 0 ? `<p><strong>Fee:</strong> $${req.fee_paid}</p>` : ''}
        <p><strong>Submitted:</strong> ${req.created_at.slice(0,10)}</p>
      </div>
    </div>`;
}

function closeModal(id) { document.getElementById(id).classList.remove('active'); }
searchDocs();
</script>
</body>
</html>"""
