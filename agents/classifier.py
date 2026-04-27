"""
Document Classifier Agent — lightweight version
Uses only the openai package. No LangChain, no LangGraph.
"""

import os
import json
import base64
import httpx
from openai import AsyncOpenAI
from db.client import get_document, update_document, insert_exception, insert_agent_log

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.8"))

SYSTEM_PROMPT = """
You are a mortgage document classifier.

Classify the document and respond ONLY with valid JSON — no markdown, no extra text:
{
  "document_type": "Paystub",
  "confidence_score": 0.95,
  "extracted_data": {
    "gross_income": 8500.00,
    "total_assets": null
  },
  "notes": "Clear paystub with YTD earnings"
}

Rules:
- document_type must be one of: Paystub, Bank Statement, W2, Other
- confidence_score is 0.0 to 1.0
- Extract gross_income from Paystubs, total_assets from Bank Statements
- Use null for fields that don't apply
"""


async def run_classifier(loan_id: str, document_id: str) -> dict:
    doc = get_document(document_id)
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    s3_url = doc.get("s3_url")
    if not s3_url:
        raise ValueError(f"Document {document_id} has no s3_url")

    # Download the file
    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.get(s3_url)
        response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    is_image = "image" in content_type

    # Build message for OpenAI
    if is_image:
        b64 = base64.b64encode(response.content).decode()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {
                    "url": f"data:{content_type};base64,{b64}",
                    "detail": "high"
                }},
                {"type": "text", "text": "Classify this mortgage document."}
            ]}
        ]
    else:
        text = response.text[:4000]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Classify this mortgage document:\n\n{text}"}
        ]

    # Call OpenAI
    completion = await client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=300,
    )

    result = json.loads(completion.choices[0].message.content)

    doc_type = result.get("document_type", "Other")
    confidence = float(result.get("confidence_score", 0.0))
    extracted = result.get("extracted_data", {})
    notes = result.get("notes", "")

    new_status = "verified" if confidence >= CONFIDENCE_THRESHOLD else "flagged"

    # Write back to Supabase
    update_document(document_id, {
        "type": doc_type,
        "confidence_score": confidence,
        "status": new_status,
        "extracted_data": extracted,
    })

    insert_agent_log(loan_id, "classifier",
        f"Classified as '{doc_type}' (confidence: {confidence:.2f}) → {new_status}")

    exception_created = False
    if confidence < CONFIDENCE_THRESHOLD:
        insert_exception(loan_id, "low_confidence", "medium",
            f"'{doc_type}' confidence {confidence:.2f} below threshold {CONFIDENCE_THRESHOLD}. {notes}")
        exception_created = True

    return {
        "document_id": document_id,
        "document_type": doc_type,
        "confidence_score": confidence,
        "status": new_status,
        "extracted_data": extracted,
        "exception_created": exception_created,
    }
