"""Direct LLM-based DPA analysis — compares full documents in a single call."""

import json
import re

from .config import ANTHROPIC_API_KEY, LLM_MODEL
from .models import Rule
from .prompts import build_system_prompt, build_user_message


_llm_client = None


def _get_llm_client():
    global _llm_client
    if _llm_client is None:
        import anthropic
        _llm_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _llm_client


def _recover_truncated_json(text: str) -> list[dict]:
    """Try to recover complete objects from a truncated JSON array.

    When the LLM response hits max_tokens, the JSON gets cut mid-object.
    This extracts all complete objects before the truncation point.
    """
    # Find all complete JSON objects in the text
    results = []
    depth = 0
    obj_start = None

    i = 0
    in_string = False
    escape_next = False

    while i < len(text):
        ch = text[i]

        if escape_next:
            escape_next = False
            i += 1
            continue

        if ch == '\\' and in_string:
            escape_next = True
            i += 1
            continue

        if ch == '"' and not escape_next:
            in_string = not in_string
            i += 1
            continue

        if in_string:
            i += 1
            continue

        if ch == '{':
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and obj_start is not None:
                try:
                    obj = json.loads(text[obj_start:i + 1])
                    results.append(obj)
                except json.JSONDecodeError:
                    pass
                obj_start = None

        i += 1

    return results


def analyze_dpa(
    input_text: str,
    playbook_text: str,
    rules: list[Rule],
    on_progress=None,
) -> list[dict]:
    """
    Analyze an incoming DPA against ClearTax playbook + rulebook in a single LLM call.

    Args:
        input_text: Full text of the incoming DPA
        playbook_text: Full text of ClearTax standard DPA
        rules: List of Rule objects from rulebook
        on_progress: Optional callback(step, total, msg)

    Returns:
        List of flag dicts, one per identified clause
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not configured. Cannot run LLM analysis.")

    if on_progress:
        on_progress(1, 3, "Building analysis prompt...")

    system_prompt = build_system_prompt(playbook_text, rules)
    user_message = build_user_message(input_text)

    if on_progress:
        on_progress(2, 3, "Calling Claude for full DPA analysis...")

    client = _get_llm_client()

    # Use streaming — required by Anthropic SDK for long-running requests
    text = ""
    stop_reason = None
    with client.messages.stream(
        model=LLM_MODEL,
        max_tokens=65536,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for chunk in stream.text_stream:
            text += chunk
        response = stream.get_final_message()
        stop_reason = response.stop_reason

    text = text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    # Try normal JSON parse first
    try:
        results = json.loads(text)
    except json.JSONDecodeError:
        # Response was likely truncated (hit max_tokens)
        if stop_reason == "max_tokens":
            print(f"  Warning: Response truncated at max_tokens. Recovering complete objects...")
            results = _recover_truncated_json(text)
            if not results:
                raise ValueError("LLM response was truncated and no complete objects could be recovered.")
            print(f"  Recovered {len(results)} complete clause analyses from truncated response.")
        else:
            raise

    if not isinstance(results, list):
        raise ValueError(f"Expected JSON array from LLM, got {type(results).__name__}")

    # Validate and fill defaults for each result.
    # Use explicit None checks — setdefault won't override keys that exist with None.
    valid_results = []
    for item in results:
        if not isinstance(item, dict):
            continue

        item["section"] = item.get("section") or ""
        item["clause_text"] = item.get("clause_text") or ""
        item["matched_playbook_section"] = item.get("matched_playbook_section") or None
        item["matched_playbook_text"] = item.get("matched_playbook_text") or None
        cls = item.get("classification") or "compliant"
        item["classification"] = "compliant" if cls == "compliant" else "non_compliant"
        item["risk_level"] = item.get("risk_level") or "Low"
        item["confidence"] = item.get("confidence") if item.get("confidence") is not None else 0.5
        item["explanation"] = item.get("explanation") or ""
        item["suggested_redline"] = item.get("suggested_redline") or ""
        item["triggered_rules"] = item.get("triggered_rules") or []

        # Skip items with no clause text at all — they're useless
        if not item["clause_text"].strip():
            continue

        # Ensure triggered_rules is a list and each entry has required fields
        if not isinstance(item["triggered_rules"], list):
            item["triggered_rules"] = []
        for tr in item["triggered_rules"]:
            if not isinstance(tr, dict):
                continue
            tr["rule_id"] = tr.get("rule_id") or ""
            tr["source"] = tr.get("source") or ""
            tr["clause"] = tr.get("clause") or ""
            tr["risk"] = tr.get("risk") or "Low"

        valid_results.append(item)

    results = valid_results

    if on_progress:
        on_progress(3, 3, f"Analysis complete — {len(results)} clauses identified")

    return results
