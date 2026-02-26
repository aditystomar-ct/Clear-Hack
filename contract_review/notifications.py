"""Slack and email notifications for review completion."""

import json
import smtplib
import urllib.request
import urllib.error
from email.mime.text import MIMEText

from .config import (
    SLACK_WEBHOOK_URL,
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM,
)


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


def send_email_notifications(
    contract_name: str,
    flags: list[dict],
    team_emails: dict[str, str],
    doc_url: str = "",
    review_id: int | None = None,
    streamlit_url: str = "http://localhost:8501",
) -> int:
    """
    Send per-team plain text emails with flagged clauses, explanations, and links.
    Each team only sees flags triggered by their own rules.
    Returns number of emails sent.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        print("  SMTP not configured — skipping email notifications.")
        return 0

    sender = EMAIL_FROM or SMTP_USER
    sent = 0

    # Group flags by team
    team_flags: dict[str, list[dict]] = {}
    for flag in flags:
        if flag["classification"] == "compliant":
            continue
        for r in flag.get("triggered_rules", []):
            team = r.get("source", "")
            if team in team_emails:
                team_flags.setdefault(team, []).append(flag)
                break

    for team, email in team_emails.items():
        tflags = team_flags.get(team, [])
        if not tflags:
            continue

        lines = []
        lines.append(f"DPA Review — {team.upper()} Team")
        lines.append("=" * 40)
        lines.append(f"Contract: {contract_name}")
        lines.append(f"Flags for your team: {len(tflags)}")
        if doc_url:
            lines.append(f"Google Doc: {doc_url}")
        if review_id:
            lines.append(f"Dashboard: {streamlit_url}?review_id={review_id}")
        lines.append("")

        for f in tflags:
            risk = f["risk_level"]
            cls = f["classification"].replace("_", " ").title()

            lines.append(f"--- {f['flag_id']} [{risk} Risk] {cls} ---")
            lines.append("")
            lines.append(f"Clause: {f.get('input_text', '')}")
            lines.append("")
            lines.append(f"Explanation: {f.get('explanation', '')}")

            # Triggered rules for this team
            team_rules = [r for r in f.get("triggered_rules", []) if r.get("source") == team]
            if team_rules:
                lines.append("")
                lines.append("Rulebook violations:")
                for r in team_rules:
                    lines.append(f"  - [{r['source'].upper()}] {r['clause']} (Risk: {r['risk']})")

            redline = f.get("suggested_redline", "")
            if redline:
                lines.append("")
                lines.append(f"Suggested redline: {redline}")

            lines.append("")

        lines.append("—")
        lines.append("DPA Contract Review Tool — ClearTax")

        body = "\n".join(lines)

        msg = MIMEText(body, "plain")
        msg["Subject"] = f"DPA Review: {len(tflags)} {team.upper()} flags — {contract_name}"
        msg["From"] = sender
        msg["To"] = email

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(sender, [email], msg.as_string())
            sent += 1
            print(f"    Email sent to {team.upper()} team: {email}")
        except Exception as e:
            print(f"    Email to {email} failed: {e}")

    return sent


def send_review_ready_email(
    contract_name: str,
    review_id: int,
    flags: list[dict],
    team_emails: dict[str, str],
    doc_url: str = "",
    base_url: str = "http://localhost:8000",
) -> int:
    """
    Send an email to each team right after analysis completes.
    Tells them how many flags are pending for their team with a direct dashboard link.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        print("  SMTP not configured — skipping review-ready emails.")
        return 0

    sender = EMAIL_FROM or SMTP_USER
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
            # General flags count for all teams
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

        lines = []
        lines.append(f"New DPA Review — Action Required")
        lines.append("=" * 40)
        lines.append("")
        lines.append(f"Contract: {contract_name}")
        lines.append(f"Review ID: #{review_id}")
        lines.append(f"Pending flags for {team.upper()} team: {count}")
        if doc_url:
            lines.append("")
            lines.append(f"Google Doc: {doc_url}")
        lines.append("")
        lines.append(f"Please review and take action on your pending flags:")
        lines.append(dashboard_url)
        lines.append("")
        lines.append("— ClearTax DPA Review Tool")

        body = "\n".join(lines)

        msg = MIMEText(body, "plain")
        msg["Subject"] = f"Action Required: {count} DPA flags pending — {contract_name}"
        msg["From"] = sender
        msg["To"] = email

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(sender, [email], msg.as_string())
            sent += 1
            print(f"    Review-ready email sent to {team.upper()}: {email}")
        except Exception as e:
            print(f"    Review-ready email to {email} failed: {e}")

    return sent


def send_all_reviewed_email(
    contract_name: str,
    review_id: int,
    team_emails: dict[str, str],
    doc_url: str = "",
    base_url: str = "http://localhost:8000",
) -> int:
    """
    Send an email to the legal team when every flag in a review has been reviewed (0 pending).
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        print("  SMTP not configured — skipping all-reviewed email.")
        return 0

    legal_email = team_emails.get("legal")
    if not legal_email:
        print("  No legal team email configured — skipping all-reviewed email.")
        return 0

    sender = EMAIL_FROM or SMTP_USER

    dashboard_url = f"{base_url}/dashboard?review={review_id}"

    lines = []
    lines.append("DPA Review Complete — All Flags Reviewed")
    lines.append("=" * 40)
    lines.append("")
    lines.append(f"Contract: {contract_name}")
    lines.append(f"Review ID: #{review_id}")
    lines.append("")
    lines.append("All pending flags have been reviewed. Please do a final review:")
    lines.append(dashboard_url)
    if doc_url:
        lines.append("")
        lines.append(f"Google Doc: {doc_url}")
    lines.append("")
    lines.append("— ClearTax DPA Review Tool")

    body = "\n".join(lines)

    msg = MIMEText(body, "plain")
    msg["Subject"] = f"All flags reviewed — {contract_name}"
    msg["From"] = sender
    msg["To"] = legal_email

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(sender, [legal_email], msg.as_string())
        print(f"    All-reviewed email sent to LEGAL: {legal_email}")
        return 1
    except Exception as e:
        print(f"    All-reviewed email to {legal_email} failed: {e}")
        return 0


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
    """
    Send a well-formatted plain text email for a single accepted flag.
    Routes to the correct team(s) based on triggered_rules source.
    Returns number of emails sent.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP not configured. Set SMTP_USER and SMTP_PASSWORD in .env to send emails."
        )

    sender = EMAIL_FROM or SMTP_USER
    sent = 0

    risk = flag.get("risk_level") or "Low"
    cls = (flag.get("classification") or "compliant").replace("_", " ").title()
    flag_id = flag.get("flag_id", "?")
    section = flag.get("input_clause_section") or "General"
    match_type = flag.get("match_type") or "N/A"

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

        L = []
        L.append(f"DPA Review — {contract_name}")
        L.append(f"Section: {section} | Risk: {risk} | {cls}")
        L.append("")
        L.append(explanation)
        if redline:
            L.append("")
            L.append(f"Suggested change: {redline}")
        if doc_url:
            L.append("")
            L.append(doc_url)
        L.append("")
        L.append("— ClearTax DPA Review Tool")

        body = "\n".join(L)

        msg = MIMEText(body, "plain")
        msg["Subject"] = f"[{risk}] DPA: {section} — {cls}"
        msg["From"] = sender
        msg["To"] = email

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(sender, [email], msg.as_string())
            sent += 1
            print(f"    Email sent to {team.upper()}: {email}")
        except Exception as e:
            raise RuntimeError(f"Email to {team.upper()} ({email}) failed: {e}") from e

    return sent
