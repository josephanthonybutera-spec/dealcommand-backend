"""
Supervisor Agent — lightweight version
Plain Python loop. No LangGraph, no complex state machines.
Detects stalled loans and escalates health scores.
"""

import os
from datetime import datetime, timezone, timedelta
from db.client import (
    get_all_active_loans,
    get_last_agent_log,
    update_loan,
    insert_exception,
    insert_agent_log,
)

STALL_HOURS = int(os.getenv("STALL_THRESHOLD_HOURS", "48"))


def is_stalled(loan: dict) -> bool:
    loan_id = loan["id"]
    last_log = get_last_agent_log(loan_id)
    threshold = timedelta(hours=STALL_HOURS)
    now = datetime.now(timezone.utc)

    if last_log:
        last_ts = datetime.fromisoformat(last_log["timestamp"].replace("Z", "+00:00"))
        return now - last_ts > threshold
    else:
        created = datetime.fromisoformat(loan["created_at"].replace("Z", "+00:00"))
        return now - created > threshold


async def run_supervisor_cycle() -> dict:
    loans = get_all_active_loans()
    escalated = []
    errors = []

    for loan in loans:
        loan_id = loan["id"]
        try:
            if is_stalled(loan):
                update_loan(loan_id, {"health_score": "Red", "status": "Stalled"})
                insert_exception(loan_id, "stalled", "high",
                    f"No activity for >{STALL_HOURS}h. Escalated to Red.")
                insert_agent_log(loan_id, "supervisor",
                    f"Loan stalled >{STALL_HOURS}h — health_score set to Red.")
                escalated.append(loan_id)
        except Exception as e:
            errors.append(f"loan {loan_id}: {str(e)}")

    return {
        "loans_checked": len(loans),
        "escalated": escalated,
        "errors": errors,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
