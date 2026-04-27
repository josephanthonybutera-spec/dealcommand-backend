from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from agents.classifier import run_classifier
from agents.chase import run_chase_agent
from agents.supervisor import run_supervisor_cycle
from db.client import (
    get_db, get_loan, get_unresolved_exceptions,
    insert_exception, insert_agent_log
)
from datetime import datetime, timezone

router = APIRouter()


# ── Request models ────────────────────────────────────────────────────

class ProcessDocumentRequest(BaseModel):
    loan_id: str
    document_id: str

class TriggerChaseRequest(BaseModel):
    loan_id: str
    missing_items: list[str] = []

class MockLOSRequest(BaseModel):
    loan_id: str
    description: str
    due_date: str | None = None

class ResolveRequest(BaseModel):
    notes: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("/process-document")
async def process_document(req: ProcessDocumentRequest):
    try:
        result = await run_classifier(req.loan_id, req.document_id)
        return {"success": True, "result": result}
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Classifier error: {e}")


@router.post("/trigger-chase")
async def trigger_chase(req: TriggerChaseRequest):
    try:
        result = await run_chase_agent(req.loan_id, req.missing_items)
        return {"success": True, "result": result}
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Chase agent error: {e}")


@router.post("/mock-los/condition")
async def mock_los_condition(req: MockLOSRequest):
    try:
        db = get_db()
        res = db.table("conditions").insert({
            "loan_id": req.loan_id,
            "description": req.description,
            "due_date": req.due_date,
            "is_met": False,
        }).execute()

        chase = await run_chase_agent(req.loan_id, [req.description])
        return {"success": True, "condition": res.data[0] if res.data else {}, "chase": chase}
    except Exception as e:
        raise HTTPException(500, f"Mock LOS error: {e}")


@router.get("/loans/{loan_id}/status")
async def loan_status(loan_id: str):
    loan = get_loan(loan_id)
    if not loan:
        raise HTTPException(404, f"Loan {loan_id} not found")

    db = get_db()
    exceptions = db.table("exceptions").select("*").eq("loan_id", loan_id).eq("resolved", False).execute().data or []
    logs = db.table("agent_logs").select("*").eq("loan_id", loan_id).order("timestamp", desc=True).limit(10).execute().data or []
    documents = db.table("documents").select("*").eq("loan_id", loan_id).execute().data or []

    return {"loan": loan, "open_exceptions": exceptions, "recent_logs": logs, "documents": documents}


@router.get("/exceptions")
async def list_exceptions():
    return {"exceptions": get_unresolved_exceptions()}


@router.post("/exceptions/{exception_id}/resolve")
async def resolve_exception(exception_id: str, req: ResolveRequest):
    db = get_db()
    res = db.table("exceptions").update({
        "resolved": True,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "notes": req.notes,
    }).eq("id", exception_id).execute()

    if not res.data:
        raise HTTPException(404, f"Exception {exception_id} not found")
    return {"success": True, "exception": res.data[0]}


@router.post("/supervisor/run")
async def run_supervisor():
    try:
        result = await run_supervisor_cycle()
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(500, f"Supervisor error: {e}")
