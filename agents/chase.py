"""
Document Chase Agent — lightweight version
Checks cooldown window, generates message via OpenAI, logs to DB.
Twilio/Gmail stubs ready to wire in Phase 2.
"""

import os
from datetime import datetime, timezone, timedelta
from openai import AsyncOpenAI
from db.client import get_loan, get_last_agent_log, insert_agent_log, insert_exception

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

COOLDOWN_HOURS = int(os.getenv("CHASE_COOLDOWN_HOURS", "24"))


def cooldown_passed(last_log: dict | None) -> bool:
    if not last_log:
        return True
    last_ts = datetime.fromisoformat(last_log["timestamp"].replace("Z", "+00:00"))
    return datetime.now(timezone.utc) - last_ts >= timedelta(hours=COOLDOWN_HOURS)


async def generate_message(loan: dict, missing_items: list[str], channel: str) -> str:
    items = ", ".join(missing_items) if missing_items else "outstanding documents"
    length_note = "Under 160 characters (SMS)." if channel == "sms" else "2-3 sentences (email)."

    completion = await client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": f"""
Write a friendly mortgage follow-up {channel} asking the borrower to provide: {items}.
Close date: {loan.get('close_date', 'TBD')}.
{length_note} Start directly, no 'Dear'.
"""}],
        temperature=0.7,
        max_tokens=100,
    )
    return completion.choices[0].message.content.strip()


async def run_chase_agent(loan_id: str, missing_items: list[str]) -> dict:
    loan = get_loan(loan_id)
    if not loan:
        raise ValueError(f"Loan {loan_id} not found")

    last_log = get_last_agent_log(loan_id, "chase")
    if not cooldown_passed(last_log):
        return {"action": "skipped", "reason": f"Within {COOLDOWN_HOURS}h cooldown"}

    # Generate both message types
    sms_msg = await generate_message(loan, missing_items, "sms")
    email_msg = await generate_message(loan, missing_items, "email")

    # Log the intended outreach (wire Twilio/Gmail here in Phase 2)
    insert_agent_log(loan_id, "chase",
        f"[PHASE 2 - SEND VIA TWILIO] SMS: {sms_msg[:80]}")
    insert_agent_log(loan_id, "chase",
        f"[PHASE 2 - SEND VIA GMAIL] Email: {email_msg[:120]}")

    return {
        "action": "outreach_drafted",
        "missing_items": missing_items,
        "sms_draft": sms_msg,
        "email_draft": email_msg,
        "note": "Messages logged. Wire Twilio/Gmail in Phase 2 to send."
    }
