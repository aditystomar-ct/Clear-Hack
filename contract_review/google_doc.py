"""Google Docs comment and highlight operations."""

import json as _json
from .auth import get_google_creds

_COMMENT_HIGHLIGHT = {"red": 1.00, "green": 0.95, "blue": 0.60}


def _build_professional_comment(flag: dict, team_emails: dict[str, str] | None = None) -> str:
    """Build a concise Google Doc comment: Concern + Proposed Amendment only."""
    cls = flag.get("classification", "compliant")
    explanation = flag.get("explanation", "")
    redline = flag.get("suggested_redline", "")

    if cls == "compliant":
        return "No concerns. This clause aligns with our standard DPA."

    comment = f"Concern: {explanation}"

    if redline:
        comment += f"\n\nProposed Amendment: {redline}"

    return comment


def clear_old_comments(doc_id: str) -> int:
    from googleapiclient.discovery import build
    creds = get_google_creds()
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    deleted = 0
    page_token = None
    while True:
        resp = drive.comments().list(
            fileId=doc_id, fields="comments(id,content),nextPageToken",
            pageToken=page_token, includeDeleted=False,
        ).execute()
        for comment in resp.get("comments", []):
            content = comment.get("content", "")
            if content.startswith("[High Risk]") or content.startswith("[Medium Risk]") or content.startswith("[Low Risk]"):
                try:
                    drive.comments().delete(fileId=doc_id, commentId=comment["id"]).execute()
                    deleted += 1
                except Exception:
                    pass
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return deleted


def add_comments_to_doc(doc_id: str, flags: list[dict], team_emails: dict[str, str] | None = None) -> int:
    from googleapiclient.discovery import build
    creds = get_google_creds()
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    docs = build("docs", "v1", credentials=creds, cache_discovery=False)
    doc = docs.documents().get(documentId=doc_id).execute()
    body_content = doc.get("body", {}).get("content", [])
    total_length = body_content[-1].get("endIndex", 0) if body_content else 0

    added = 0
    for flag in flags:
        if flag["classification"] == "compliant":
            continue

        risk = flag["risk_level"]
        cls = flag["classification"].replace("_", " ").title()

        rule_lines = []
        tagged_teams = set()
        for r in flag["triggered_rules"]:
            rule_lines.append(f"  - [{r['source'].upper()}] {r['clause']} (Risk: {r['risk']})")
            tagged_teams.add(r["source"])

        comment_text = f"[{risk} Risk] {cls}\n\n{flag['explanation']}\n"
        if rule_lines:
            comment_text += "\nRulebook violations:\n" + "\n".join(rule_lines) + "\n"
        if flag["suggested_redline"]:
            comment_text += f"\nSuggested redline:\n{flag['suggested_redline']}"

        # Add reviewer emails in comment
        if team_emails and tagged_teams:
            tags = [f"{t.upper()}: {team_emails[t]}" for t in tagged_teams if t in team_emails]
            if tags:
                comment_text += "\n\nReviewer: " + ", ".join(tags)

        start = flag.get("start_index", 0)
        end = flag.get("end_index", 0)

        anchor = _json.dumps({
            "r": "head",
            "a": [{"txt": {"o": start, "l": end - start, "ml": total_length}}],
        })

        body = {
            "content": comment_text,
            "anchor": anchor,
        }

        try:
            drive.comments().create(fileId=doc_id, body=body, fields="id,anchor").execute()
            added += 1
        except Exception as e:
            print(f"    Could not add comment for {flag['flag_id']}: {e}")

    return added


def clear_old_highlights(doc_id: str, flags: list[dict]) -> None:
    from googleapiclient.discovery import build
    creds = get_google_creds()
    docs = build("docs", "v1", credentials=creds, cache_discovery=False)

    requests = []
    for flag in flags:
        start = flag.get("start_index", 0)
        end = flag.get("end_index", 0)
        if start >= end:
            continue
        requests.append({
            "updateTextStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "textStyle": {"backgroundColor": {"color": {"rgbColor": {"red": 1, "green": 1, "blue": 1}}}},
                "fields": "backgroundColor",
            }
        })
    if requests:
        docs.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()


def highlight_flagged_paragraphs(doc_id: str, flags: list[dict]) -> int:
    from googleapiclient.discovery import build
    creds = get_google_creds()
    docs = build("docs", "v1", credentials=creds, cache_discovery=False)

    requests = []
    for flag in flags:
        if flag["classification"] == "compliant":
            continue
        start = flag.get("start_index", 0)
        end = flag.get("end_index", 0)
        if start >= end:
            continue
        requests.append({
            "updateTextStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "textStyle": {"backgroundColor": {"color": {"rgbColor": _COMMENT_HIGHLIGHT}}},
                "fields": "backgroundColor",
            }
        })

    if not requests:
        return 0
    BATCH_SIZE = 50
    for chunk_start in range(0, len(requests), BATCH_SIZE):
        chunk = requests[chunk_start: chunk_start + BATCH_SIZE]
        docs.documents().batchUpdate(documentId=doc_id, body={"requests": chunk}).execute()
    return len(requests)


def add_comment_single(doc_id: str, flag: dict, team_emails: dict[str, str] | None = None) -> bool:
    """Add a single comment to Google Doc for one flag. No classification filtering."""
    from googleapiclient.discovery import build
    creds = get_google_creds()
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    docs = build("docs", "v1", credentials=creds, cache_discovery=False)

    doc = docs.documents().get(documentId=doc_id).execute()
    body_content = doc.get("body", {}).get("content", [])
    total_length = body_content[-1].get("endIndex", 0) if body_content else 0

    comment_text = _build_professional_comment(flag, team_emails)

    start = flag.get("start_index", 0)
    end = flag.get("end_index", 0)

    anchor = _json.dumps({
        "r": "head",
        "a": [{"txt": {"o": start, "l": end - start, "ml": total_length}}],
    })

    body = {"content": comment_text, "anchor": anchor}

    try:
        drive.comments().create(fileId=doc_id, body=body, fields="id,anchor").execute()
        return True
    except Exception as e:
        raise RuntimeError(f"Could not add comment for {flag.get('flag_id', '?')}: {e}") from e


def highlight_single(doc_id: str, flag: dict) -> bool:
    """Highlight a single flag's text range on Google Doc. No classification filtering."""
    from googleapiclient.discovery import build
    creds = get_google_creds()
    docs = build("docs", "v1", credentials=creds, cache_discovery=False)

    start = flag.get("start_index", 0)
    end = flag.get("end_index", 0)
    if start >= end:
        return False

    request = {
        "updateTextStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "textStyle": {"backgroundColor": {"color": {"rgbColor": _COMMENT_HIGHLIGHT}}},
            "fields": "backgroundColor",
        }
    }

    try:
        docs.documents().batchUpdate(documentId=doc_id, body={"requests": [request]}).execute()
        return True
    except Exception as e:
        print(f"    Could not highlight {flag.get('flag_id', '?')}: {e}")
        return False


def post_manual_comment(doc_id: str, flag: dict, comment_text: str) -> bool:
    """Post a custom reviewer comment to Google Doc anchored at the flag's position."""
    from googleapiclient.discovery import build
    creds = get_google_creds()
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    docs = build("docs", "v1", credentials=creds, cache_discovery=False)

    doc = docs.documents().get(documentId=doc_id).execute()
    body_content = doc.get("body", {}).get("content", [])
    total_length = body_content[-1].get("endIndex", 0) if body_content else 0

    start = flag.get("start_index", 0)
    end = flag.get("end_index", 0)

    anchor = _json.dumps({
        "r": "head",
        "a": [{"txt": {"o": start, "l": end - start, "ml": total_length}}],
    })

    body = {"content": comment_text, "anchor": anchor}

    try:
        drive.comments().create(fileId=doc_id, body=body, fields="id,anchor").execute()
        return True
    except Exception as e:
        raise RuntimeError(f"Could not post comment for {flag.get('flag_id', '?')}: {e}") from e
