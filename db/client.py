import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client = None


def get_db() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        _client = create_client(url, key)
    return _client


def get_document(document_id: str):
    res = get_db().table("documents").select("*").eq("id", document_id).single().execute()
    return res.data


def update_document(document_id: str, fields: dict):
    get_db().table("documents").update(fields).eq("id", document_id).execute()


def get_loan(loan_id: str):
    res = get_db().table("loans").select("*").eq("id", loan_id).single().execute()
    return res.data


def update_loan(loan_id: str, fields: dict):
    get_db().table("loans").update(fields).eq("id", loan_id).execute()


def insert_exception(loan_id: str, exc_type: str, severity: str, notes: str = ""):
    get_db().table("exceptions").insert({
        "loan_id": loan_id,
        "type": exc_type,
        "severity": severity,
        "notes": notes,
        "resolved": False,
    }).execute()


def insert_agent_log(loan_id: str, agent_name: str, action: str):
    get_db().table("agent_logs").insert({
        "loan_id": loan_id,
        "agent_name": agent_name,
        "action_taken": action,
    }).execute()


def get_last_agent_log(loan_id: str, agent_name: str = "chase"):
    res = (
        get_db().table("agent_logs")
        .select("*")
        .eq("loan_id", loan_id)
        .eq("agent_name", agent_name)
        .order("timestamp", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_all_active_loans():
    res = get_db().table("loans").select("*").neq("status", "Closed").execute()
    return res.data or []


def get_unresolved_exceptions():
    res = get_db().table("exceptions").select("*").eq("resolved", False).execute()
    return res.data or []
