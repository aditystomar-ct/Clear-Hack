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


def send_flag_email(
    contract_name: str,
    flag: dict,
    team_emails: dict[str, str],
    doc_url: str = "",
) -> int:
    """
    Send plain text email for a single accepted flag.
    Routes to the correct team(s) based on triggered_rules source:
      - Flag has legal rules → email to legal team
      - Flag has infosec rules → email to infosec team
      - Flag has both → email to both
      - Flag has no triggered rules → email to all teams
    Returns number of emails sent.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        print("  SMTP not configured — skipping email.")
        return 0

    sender = EMAIL_FROM or SMTP_USER
    sent = 0

    risk = flag["risk_level"]
    cls = flag["classification"].replace("_", " ").title()

    # Determine which teams to email based on triggered rules
    triggered_teams = set()
    for r in flag.get("triggered_rules", []):
        src = r.get("source", "")
        if src in team_emails:
            triggered_teams.add(src)

    # If no rules triggered, send to all teams
    if not triggered_teams:
        triggered_teams = set(team_emails.keys())

    for team in triggered_teams:
        email = team_emails.get(team)
        if not email:
            continue

        lines = []
        lines.append(f"DPA Review — {team.upper()} Team")
        lines.append("=" * 40)
        lines.append(f"Contract: {contract_name}")
        if doc_url:
            lines.append(f"Google Doc: {doc_url}")
        lines.append(f"Sent to: {email}")
        lines.append("")

        lines.append(f"--- {flag.get('flag_id', '?')} [{risk} Risk] {cls} ---")
        lines.append("")
        lines.append(f"Clause: {flag.get('input_text', '')}")
        lines.append("")
        lines.append(f"Explanation: {flag.get('explanation', '')}")

        # Show only this team's rules
        team_rules = [r for r in flag.get("triggered_rules", []) if r.get("source") == team]
        if team_rules:
            lines.append("")
            lines.append("Rulebook violations:")
            for r in team_rules:
                lines.append(f"  - [{r['source'].upper()}] {r['clause']} (Risk: {r['risk']})")

        redline = flag.get("suggested_redline", "")
        if redline:
            lines.append("")
            lines.append(f"Suggested redline: {redline}")

        lines.append("")
        lines.append("—")
        lines.append("DPA Contract Review Tool — ClearTax")

        body = "\n".join(lines)

        msg = MIMEText(body, "plain")
        msg["Subject"] = f"[{team.upper()}] DPA Flag Accepted: {flag.get('flag_id', '?')} [{risk} Risk] — {contract_name}"
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
            print(f"    Email to {email} failed: {e}")

    return sent
