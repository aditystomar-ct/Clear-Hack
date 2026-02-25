"""Slack notifications for review completion."""

import json
import urllib.request
import urllib.error

from .config import SLACK_WEBHOOK_URL


def send_slack_notification(contract_name, summary, review_id, streamlit_url="http://localhost:8501"):
    if not SLACK_WEBHOOK_URL:
        return False

    risk_bd = summary.get("risk_breakdown", {})
    cls_bd = summary.get("classification_breakdown", {})

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
