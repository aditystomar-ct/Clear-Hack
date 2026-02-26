"""Slack and email notifications for review completion."""

import json
import smtplib
import urllib.request
import urllib.error
from email.mime.text import MIMEText

from .config import (
    SLACK_WEBHOOK_URL,
    RESEND_API_KEY, EMAIL_FROM,
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
)


# ---------------------------------------------------------------------------
# Low-level email sender — Resend (HTTP) or SMTP fallback
# ---------------------------------------------------------------------------

def _send_email(to: str, subject: str, body: str):
    """Send a single email. Uses Resend API if configured, else SMTP."""
    if RESEND_API_KEY:
        return _send_via_resend(to, subject, body)
    if SMTP_USER and SMTP_PASSWORD:
        return _send_via_smtp(to, subject, body)
    raise RuntimeError("No email provider configured. Set RESEND_API_KEY or SMTP_USER/SMTP_PASSWORD.")


def _send_via_resend(to: str, subject: str, body: str):
    """Send email via Resend HTTP API — works on Render (no SMTP port needed)."""
    import resend
    resend.api_key = RESEND_API_KEY
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [to],
        "subject": subject,
        "text": body,
    })


def _send_via_smtp(to: str, subject: str, body: str):
    """Send email via SMTP — works locally with Gmail App Password."""
    sender = EMAIL_FROM or SMTP_USER
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(sender, [to], msg.as_string())


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------

def send_slack_notification(contract_name, summary, review_id, streamlit_url="http://localhost:8501"):
    if not SLACK_WEBHOOK_URL:
        return False

    risk_bd = summary.get("risk_breakdown", {})

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "DPA Review Complete"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Contract:*\n{contract_name}"},
            {"type": "mrkdwn", "text": f"*Review ID:*\n#{review_id}"},
            {"type": "mrkdwn", "text": f"*Total Clauses:*\n{summary.get('total_clauses_analyzed', 0)}"},
            {"type": "mrkdwn", "text": f"*High Risk:*\n{risk_bd.get('High', 0)}"},
        ]},
        {"type": "actions", "elements": [{
            "type": "button",
            "text": {"type": "plain_text", "text": "Open Review Dashboard"},
            "url": f"{streamlit_url}?review_id={review_id}",
            "style": "primary",
        }]},
    ]

    payload = json.dumps({"blocks": blocks}).encode("utf-8")
    try:
        req = urllib.request.Request(SLACK_WEBHOOK_URL, data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  Slack notification failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Review-ready email (sent after analysis completes)
# ---------------------------------------------------------------------------

def send_review_ready_email(
    contract_name: str,
    review_id: int,
    flags: list[dict],
    team_emails: dict[str, str],
    doc_url: str = "",
    base_url: str = "http://localhost:8000",
) -> int:
    """Send an email to each team right after analysis completes."""
    sent = 0

    # Count flags per team
    team_flag_counts: dict[str, int] = {}
    for flag in flags:
        if flag.get("classification") == "compliant":
            continue
        triggered_teams = set()
        for r in flag.get("triggered_rules", []):
            src = r.get("source", "")
            if src in team_emails:
                triggered_teams.add(src)
        if not triggered_teams:
            for t in team_emails:
                team_flag_counts[t] = team_flag_counts.get(t, 0) + 1
        else:
            for t in triggered_teams:
                team_flag_counts[t] = team_flag_counts.get(t, 0) + 1

    for team, email in team_emails.items():
        count = team_flag_counts.get(team, 0)
        if count == 0:
            continue

        dashboard_url = f"{base_url}/dashboard?review={review_id}&tab={team}"

        lines = [
            f"New DPA Review — Action Required",
            "=" * 40,
            "",
            f"Contract: {contract_name}",
            f"Review ID: #{review_id}",
            f"Pending flags for {team.upper()} team: {count}",
        ]
        if doc_url:
            lines += ["", f"Google Doc: {doc_url}"]
        lines += [
            "",
            f"Please review and take action on your pending flags:",
            dashboard_url,
            "",
            "— ClearTax DPA Review Tool",
        ]

        subject = f"Action Required: {count} DPA flags pending — {contract_name}"
        try:
            _send_email(email, subject, "\n".join(lines))
            sent += 1
            print(f"    Review-ready email sent to {team.upper()}: {email}")
        except Exception as e:
            print(f"    Review-ready email to {email} failed: {e}")

    return sent


# ---------------------------------------------------------------------------
# All-reviewed email (sent when all flags have been actioned)
# ---------------------------------------------------------------------------

def send_all_reviewed_email(
    contract_name: str,
    review_id: int,
    team_emails: dict[str, str],
    doc_url: str = "",
    base_url: str = "http://localhost:8000",
) -> int:
    """Send an email to the legal team when every flag has been reviewed."""
    legal_email = team_emails.get("legal")
    if not legal_email:
        print("  No legal team email configured — skipping all-reviewed email.")
        return 0

    dashboard_url = f"{base_url}/dashboard?review={review_id}"

    lines = [
        "DPA Review Complete — All Flags Reviewed",
        "=" * 40,
        "",
        f"Contract: {contract_name}",
        f"Review ID: #{review_id}",
        "",
        "All pending flags have been reviewed. Please do a final review:",
        dashboard_url,
    ]
    if doc_url:
        lines += ["", f"Google Doc: {doc_url}"]
    lines += ["", "— ClearTax DPA Review Tool"]

    subject = f"All flags reviewed — {contract_name}"
    try:
        _send_email(legal_email, subject, "\n".join(lines))
        print(f"    All-reviewed email sent to LEGAL: {legal_email}")
        return 1
    except Exception as e:
        print(f"    All-reviewed email to {legal_email} failed: {e}")
        return 0


# ---------------------------------------------------------------------------
# Single flag email (sent when a flag is accepted)
# ---------------------------------------------------------------------------

def _truncate_clause(text: str, max_len: int = 300) -> str:
    """Shorten long clause text for email readability."""
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + " [...]"


def _risk_label(risk: str) -> str:
    labels = {"High": "HIGH RISK", "Medium": "MEDIUM RISK", "Low": "LOW RISK"}
    return labels.get(risk, risk.upper())


def send_flag_email(
    contract_name: str,
    flag: dict,
    team_emails: dict[str, str],
    doc_url: str = "",
) -> int:
    """Send an email for a single accepted flag to the relevant team(s)."""
    sent = 0

    risk = flag.get("risk_level") or "Low"
    cls = (flag.get("classification") or "compliant").replace("_", " ").title()
    section = flag.get("input_clause_section") or "General"

    # Determine which teams to email
    triggered_teams = set()
    for r in flag.get("triggered_rules", []):
        src = r.get("source", "")
        if src in team_emails:
            triggered_teams.add(src)
    if not triggered_teams:
        triggered_teams = set(team_emails.keys())

    for team in triggered_teams:
        email = team_emails.get(team)
        if not email:
            continue

        explanation = flag.get("explanation") or ""
        redline = flag.get("suggested_redline") or ""

        lines = [
            f"DPA Review — {contract_name}",
            f"Section: {section} | Risk: {risk} | {cls}",
            "",
            explanation,
        ]
        if redline:
            lines += ["", f"Suggested change: {redline}"]
        if doc_url:
            lines += ["", doc_url]
        lines += ["", "— ClearTax DPA Review Tool"]

        subject = f"[{risk}] DPA: {section} — {cls}"
        try:
            _send_email(email, subject, "\n".join(lines))
            sent += 1
            print(f"    Email sent to {team.upper()}: {email}")
        except Exception as e:
            raise RuntimeError(f"Email to {team.upper()} ({email}) failed: {e}") from e

    return sent
