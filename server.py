"""FastAPI backend for DPA Contract Review Tool.

Wraps the existing contract_review/ package as REST API endpoints.
Serves the built React frontend in production.
"""

import json
import os
import tempfile
import threading
import traceback
from pathlib import Path
from queue import Empty, Queue

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

# Ensure .env is loaded before importing contract_review
BASE_DIR = Path(__file__).parent
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip("\"'"))

from contract_review.config import (
    ANTHROPIC_API_KEY,
    LLM_MODEL,
    RULEBOOK_PATH,
    SMTP_USER,
)
from contract_review.database import (
    get_review,
    get_review_flags,
    get_review_stats,
    get_rule_effectiveness,
    list_reviews,
    update_flag_action,
)
from contract_review.extractors import load_team_emails

app = FastAPI(title="DPA Contract Review API")

BASE_URL = os.environ.get("BASE_URL", "https://clear-hack.onrender.com")


def _check_all_reviewed(review_id: int):
    """If no pending flags remain, email all teams that review is complete."""
    flag_actions = get_review_flags(review_id)
    pending = sum(1 for fa in flag_actions if fa["reviewer_action"] == "pending")
    if pending > 0:
        return

    review = get_review(review_id)
    if not review:
        return

    metadata = json.loads(review["metadata_json"]) if review["metadata_json"] else {}
    doc_id = metadata.get("input_source", "")
    is_google_doc = doc_id and not doc_id.endswith(".docx") and len(doc_id) > 15
    doc_url = f"https://docs.google.com/document/d/{doc_id}" if is_google_doc else ""

    try:
        from contract_review.notifications import send_all_reviewed_email

        team_emails = load_team_emails(RULEBOOK_PATH)
        send_all_reviewed_email(
            contract_name=review["contract_name"],
            review_id=review_id,
            team_emails=team_emails,
            doc_url=doc_url,
            base_url=BASE_URL,
        )
    except Exception as e:
        print(f"  All-reviewed email failed: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# GET /api/config — LLM availability check
# ---------------------------------------------------------------------------
@app.get("/api/config")
def api_config():
    return {
        "llm_available": bool(ANTHROPIC_API_KEY),
        "llm_model": LLM_MODEL,
        "smtp_configured": bool(SMTP_USER),
    }


# ---------------------------------------------------------------------------
# GET /api/reviews — List all reviews
# ---------------------------------------------------------------------------
@app.get("/api/reviews")
def api_list_reviews():
    return list_reviews()


# ---------------------------------------------------------------------------
# GET /api/reviews/{id} — Single review with parsed JSON
# ---------------------------------------------------------------------------
@app.get("/api/reviews/{review_id}")
def api_get_review(review_id: int):
    review = get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return {
        "id": review["id"],
        "contract_name": review["contract_name"],
        "date": review["date"],
        "reviewer": review["reviewer"],
        "status": review["status"],
        "analysis_mode": review["analysis_mode"],
        "summary": json.loads(review["summary_json"]) if review["summary_json"] else {},
        "metadata": json.loads(review["metadata_json"]) if review["metadata_json"] else {},
        "flags": json.loads(review["flags_json"]) if review["flags_json"] else [],
    }


# ---------------------------------------------------------------------------
# GET /api/reviews/{id}/flags — Flag actions for review
# ---------------------------------------------------------------------------
@app.get("/api/reviews/{review_id}/flags")
def api_get_review_flags(review_id: int):
    return get_review_flags(review_id)


# ---------------------------------------------------------------------------
# PATCH /api/reviews/{id}/flags/{flag_id} — Mark as closed
# ---------------------------------------------------------------------------
@app.patch("/api/reviews/{review_id}/flags/{flag_id}")
def api_update_flag(review_id: int, flag_id: str, body: dict):
    action = body.get("action", "closed")
    note = body.get("note", "")
    reviewer_name = body.get("reviewer_name", "")
    update_flag_action(review_id, flag_id, action, note, reviewer_name)
    _check_all_reviewed(review_id)
    return {"flag_id": flag_id, "status": action}


# ---------------------------------------------------------------------------
# POST /api/reviews/{id}/flags/{flag_id}/accept — Accept: comment + highlight + email
# ---------------------------------------------------------------------------
@app.post("/api/reviews/{review_id}/flags/{flag_id}/accept")
def api_accept_flag(review_id: int, flag_id: str, body: dict):
    review = get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    flags = json.loads(review["flags_json"])
    flag = next((f for f in flags if f["flag_id"] == flag_id), None)
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")

    metadata = json.loads(review["metadata_json"]) if review["metadata_json"] else {}
    custom_comment = body.get("comment", "").strip()
    reviewer_name = body.get("reviewer_name", review.get("reviewer", ""))

    # Update DB immediately
    update_flag_action(review_id, flag_id, "accepted", custom_comment, reviewer_name)

    # Run slow tasks (Google Doc + email) in background thread
    def _background_tasks():
        doc_id = metadata.get("input_source", "")
        is_google_doc = doc_id and not doc_id.endswith(".docx") and len(doc_id) > 15
        team_emails = load_team_emails(RULEBOOK_PATH)

        if is_google_doc:
            try:
                from contract_review.google_doc import (
                    highlight_single,
                    post_manual_comment,
                )
                post_manual_comment(doc_id, flag, custom_comment)
                highlight_single(doc_id, flag)
            except Exception as e:
                print(f"  Google Doc update failed: {e}")

        try:
            from contract_review.notifications import send_flag_email
            doc_url = f"https://docs.google.com/document/d/{doc_id}" if is_google_doc else ""
            send_flag_email(
                contract_name=metadata.get("contract_name", metadata.get("input_source", "")),
                flag=flag,
                team_emails=team_emails,
                doc_url=doc_url,
            )
        except Exception as e:
            print(f"  Email failed: {e}")

        _check_all_reviewed(review_id)

    threading.Thread(target=_background_tasks, daemon=True).start()

    return {
        "flag_id": flag_id,
        "status": "accepted",
    }


# ---------------------------------------------------------------------------
# GET /api/stats — Aggregate stats
# ---------------------------------------------------------------------------
@app.get("/api/stats")
def api_stats():
    return get_review_stats()


# ---------------------------------------------------------------------------
# GET /api/rules/effectiveness — Rule effectiveness
# ---------------------------------------------------------------------------
@app.get("/api/rules/effectiveness")
def api_rule_effectiveness():
    return get_rule_effectiveness()


# ---------------------------------------------------------------------------
# GET /api/teams — Team email mapping
# ---------------------------------------------------------------------------
@app.get("/api/teams")
def api_teams():
    return load_team_emails(RULEBOOK_PATH)


# ---------------------------------------------------------------------------
# POST /api/analyze — Start analysis with SSE progress stream
# ---------------------------------------------------------------------------
@app.post("/api/analyze")
async def api_analyze(
    file: UploadFile | None = File(None),
    url: str = Form(""),
    reviewer: str = Form(""),
    playbook: str = Form(""),
):
    if not file and not url.strip():
        raise HTTPException(status_code=400, detail="Provide a file or URL")

    # Save uploaded file to temp dir if provided
    if file:
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, file.filename)
        with open(tmp_path, "wb") as f:
            content = await file.read()
            f.write(content)
        input_source = tmp_path
    else:
        input_source = url.strip()

    playbook_source = playbook.strip() if playbook.strip() else None

    q: Queue = Queue()

    def run_in_thread():
        try:
            from contract_review.pipeline import run_pipeline

            def progress_callback(step, total, msg):
                q.put({"type": "progress", "step": step, "total": total, "message": msg})

            result = run_pipeline(
                input_source=input_source,
                playbook_source=playbook_source,
                reviewer=reviewer,
                progress_callback=progress_callback,
            )

            # Send review-ready emails to legal & infosec teams immediately
            try:
                from contract_review.notifications import send_review_ready_email

                team_emails = load_team_emails(RULEBOOK_PATH)
                meta = result.get("metadata", {})
                doc_id = meta.get("input_source", "")
                is_gdoc = doc_id and not doc_id.endswith(".docx") and len(doc_id) > 15
                doc_url = f"https://docs.google.com/document/d/{doc_id}" if is_gdoc else ""

                send_review_ready_email(
                    contract_name=meta.get("contract_name", doc_id),
                    review_id=result["review_id"],
                    flags=result["flags"],
                    team_emails=team_emails,
                    doc_url=doc_url,
                    base_url=BASE_URL,
                )
            except Exception as e:
                print(f"  Review-ready email failed: {e}")

            q.put({"type": "complete", "data": result})
        except Exception as e:
            q.put({"type": "error", "message": str(e), "traceback": traceback.format_exc()})

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()

    def event_stream():
        while True:
            try:
                # Short timeout so we can send keepalive pings while the LLM thinks
                event = q.get(timeout=15)
            except Empty:
                # No event yet — send a keepalive comment to prevent connection timeout
                yield ": keepalive\n\n"
                # Check if the thread is still alive (give up after 10 minutes total)
                if not thread.is_alive():
                    yield "data: {\"type\": \"error\", \"message\": \"Pipeline thread died unexpectedly\"}\n\n"
                    break
                continue
            yield f"data: {json.dumps(event)}\n\n"
            if event["type"] in ("complete", "error"):
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Serve React static files in production
# ---------------------------------------------------------------------------
_frontend_dist = BASE_DIR / "frontend" / "dist"
if _frontend_dist.exists():
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")

    # Catch-all: serve index.html for client-side routing
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # If the file exists in dist, serve it directly
        file_path = _frontend_dist / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        # Otherwise serve index.html for client-side routing
        return FileResponse(str(_frontend_dist / "index.html"))
