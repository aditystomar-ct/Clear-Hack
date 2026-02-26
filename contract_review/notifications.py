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
        print("  SMTP not configured — skipping email.")
        return 0

    sender = EMAIL_FROM or SMTP_USER
    sent = 0

    risk = flag["risk_level"]
    cls = flag["classification"].replace("_", " ").title()
    flag_id = flag.get("flag_id", "?")
    section = flag.get("input_clause_section") or "General"
    similarity = flag.get("similarity_score", 0)
    match_type = flag.get("match_type", "N/A")

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

        L = []

        # --- Header ---
        L.append(f"DPA CLAUSE REVIEW — {team.upper()} TEAM")
        L.append("")
        L.append(f"A clause from the incoming DPA has been reviewed and accepted.")
        L.append(f"Your team's attention is required for the item below.")
        L.append("")

        # --- Quick summary box ---
        L.append("+------------------------------------------------------+")
        L.append(f"|  Flag:           {flag_id}")
        L.append(f"|  Risk:           {_risk_label(risk)}")
        L.append(f"|  Classification: {cls}")
        L.append(f"|  Section:        {section}")
        L.append(f"|  Similarity:     {similarity:.0%} ({match_type})")
        L.append("+------------------------------------------------------+")
        L.append("")

        # --- Clause text ---
        L.append("CLAUSE TEXT")
        L.append("-" * 40)
        clause_text = flag.get("input_text", "")
        L.append(_truncate_clause(clause_text))
        L.append("")

        # --- Playbook comparison (if available) ---
        pb_text = flag.get("matched_playbook_text", "")
        if pb_text:
            L.append("CLEARTAX PLAYBOOK (EXPECTED)")
            L.append("-" * 40)
            L.append(_truncate_clause(pb_text))
            L.append("")

        # --- Analysis ---
        explanation = flag.get("explanation", "")
        if explanation:
            L.append("ANALYSIS")
            L.append("-" * 40)
            L.append(explanation)
            L.append("")

        # --- Rulebook violations for this team ---
        team_rules = [r for r in flag.get("triggered_rules", []) if r.get("source") == team]
        if team_rules:
            L.append(f"RULEBOOK VIOLATIONS ({team.upper()})")
            L.append("-" * 40)
            for r in team_rules:
                L.append(f"  * {r['clause']}")
                L.append(f"    Risk: {r['risk']}")
            L.append("")

        # --- Suggested redline ---
        redline = flag.get("suggested_redline", "")
        if redline:
            L.append("SUGGESTED REDLINE")
            L.append("-" * 40)
            L.append(redline)
            L.append("")

        # --- Action needed ---
        L.append("NEXT STEPS")
        L.append("-" * 40)
        if risk == "High":
            L.append("This clause requires immediate review. Please check the")
            L.append("Google Doc and add your comments or approve the redline.")
        elif risk == "Medium":
            L.append("This clause has moderate deviations. Please review the")
            L.append("flagged text and confirm or suggest changes.")
        else:
            L.append("This clause has been flagged for your awareness.")
            L.append("No urgent action needed, but please review when convenient.")
        L.append("")

        # --- Links ---
        if doc_url:
            L.append(f"View Document: {doc_url}")
        L.append("")

        # --- Footer ---
        L.append("---")
        L.append("DPA Contract Review Tool | ClearTax")
        L.append("This is an automated notification. Do not reply to this email.")

        body = "\n".join(L)

        # Subject line: concise and scannable
        risk_emoji = {"High": "[!]", "Medium": "[~]", "Low": "[i]"}.get(risk, "")
        msg = MIMEText(body, "plain")
        msg["Subject"] = f"{risk_emoji} DPA Review: {flag_id} — {section} ({cls}) — {team.upper()}"
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
