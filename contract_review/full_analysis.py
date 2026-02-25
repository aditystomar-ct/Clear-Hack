"""
Full-context LLM analysis — sends each paragraph to Claude with the
complete ClearTax playbook + rulebook as context.
No vector similarity, no heuristic. Pure LLM understanding.
"""

import json
from pathlib import Path

from .config import ANTHROPIC_API_KEY, LLM_MODEL, PLAYBOOK_PATH, RULEBOOK_PATH
from .extractors import load_rulebook


def _load_playbook_text(path: Path = PLAYBOOK_PATH) -> str:
    """Load the full text of the ClearTax DPA playbook."""
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())


def _load_rules_text(path: Path = RULEBOOK_PATH) -> str:
    """Load all rules as formatted text for the prompt."""
    rules = load_rulebook(path)
    lines = []
    for r in rules:
        lines.append(
            f"[{r.rule_id}] {r.source.upper()} | Clause: {r.clause} | "
            f"Risk: {r.risk}\n"
            f"  Trigger: {r.subclause}\n"
            f"  Required Response: {r.response}"
        )
    return "\n\n".join(lines), rules


def build_system_prompt() -> str:
    """Build the system prompt with full playbook + rulebook knowledge."""
    playbook_text = _load_playbook_text()
    rules_text, rules = _load_rules_text()

    return f"""You are a senior legal and compliance expert at ClearTax (Defmacro Software Pvt Ltd).
ClearTax is the DATA PROCESSOR / SERVICE PROVIDER.
The incoming DPA you are reviewing is from a customer who is the DATA CONTROLLER.

You have COMPLETE knowledge of ClearTax's standard DPA template and internal rulebook.
Your job: For each paragraph I give you from the incoming DPA, decide if it is acceptable to ClearTax or if it deviates from ClearTax's standard position.

=============================================
CLEARTAX'S STANDARD DPA TEMPLATE (PLAYBOOK)
=============================================
{playbook_text}

=============================================
CLEARTAX'S INTERNAL RULEBOOK
=============================================
These are specific red flags that ClearTax's legal and infosec teams watch for.
If a paragraph triggers any of these rules, it MUST be flagged.

{rules_text}

=============================================
DECISION CRITERIA
=============================================

PASS — The paragraph is acceptable to ClearTax:
  - Text that matches or is substantially similar to ClearTax's standard DPA template
  - Standard legal boilerplate (definitions, preamble, recitals, signatures, exhibit headers)
  - Section headers, clause numbers, titles
  - Paragraphs that don't create obligations unfavorable to ClearTax
  - Obligations that are the SAME or LESS onerous than ClearTax's standard

FLAG — The paragraph deviates from ClearTax's interests:
  - Obligations that are MORE onerous than what ClearTax's standard template provides
  - Missing protections or rights that ClearTax's template includes for the Processor
  - Clauses that trigger any rulebook rule
  - Terms unfavorable to ClearTax as a processor (e.g., unlimited liability, direct audit rights, consent-based subprocessor approval, compliance with non-GDPR laws, customer-controlled breach notification)
  - New obligations not present in ClearTax's standard template that increase ClearTax's risk
  - Shorter timelines than ClearTax's standard (e.g., 24 hours instead of 60 days for data deletion)

IMPORTANT:
  - Be precise. Do NOT flag paragraphs just because they use different wording — flag only when the SUBSTANCE differs from ClearTax's position.
  - A paragraph that says the same thing as ClearTax's template in different words is a PASS.
  - Focus on what MATTERS to ClearTax as the processor.

=============================================
OUTPUT FORMAT
=============================================
Respond ONLY with valid JSON (no markdown fences, no extra text):
{{
  "decision": "flag" or "pass",
  "classification": "compliant" or "deviation_minor" or "deviation_major" or "non_compliant",
  "risk_level": "High" or "Medium" or "Low",
  "explanation": "Brief clear explanation of why this is flagged or passed",
  "suggested_redline": "What ClearTax should request instead (empty string if pass)",
  "confidence": 0.85,
  "relevant_playbook_section": "Which section of ClearTax template this relates to (or 'N/A')",
  "triggered_rules": ["rule_id_1"]
}}

Rules for classification:
- "compliant" = acceptable, matches ClearTax standard (PASS)
- "deviation_minor" = small difference, low business impact (FLAG)
- "deviation_major" = significant deviation, needs negotiation (FLAG)
- "non_compliant" = completely unacceptable to ClearTax (FLAG)

For PASS decisions: classification must be "compliant", risk_level "Low", suggested_redline "", triggered_rules [].
"""


def analyze_paragraph(
    system_prompt: str,
    paragraph_text: str,
    paragraph_number: int,
) -> dict:
    """
    Analyze a single paragraph against the full playbook + rulebook context.
    Returns the analysis dict from Claude.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_message = f"""PARAGRAPH {paragraph_number}:
\"{paragraph_text}\""""

    try:
        resp = client.messages.create(
            model=LLM_MODEL,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        text = resp.content[0].text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(text)

        # Ensure all required fields exist
        result.setdefault("decision", "pass")
        result.setdefault("classification", "compliant")
        result.setdefault("risk_level", "Low")
        result.setdefault("explanation", "")
        result.setdefault("suggested_redline", "")
        result.setdefault("confidence", 0.5)
        result.setdefault("relevant_playbook_section", "N/A")
        result.setdefault("triggered_rules", [])
        return result

    except Exception as e:
        print(f"    LLM error on paragraph {paragraph_number}: {e}")
        return {
            "decision": "pass",
            "classification": "compliant",
            "risk_level": "Low",
            "explanation": f"LLM error: {e}. Defaulting to pass.",
            "suggested_redline": "",
            "confidence": 0.0,
            "relevant_playbook_section": "N/A",
            "triggered_rules": [],
        }


def build_flag_from_analysis(
    idx: int,
    paragraph: dict,
    analysis: dict,
) -> dict:
    """Build a flag dict from a paragraph + analysis result."""
    return {
        "flag_id": f"FLAG_{idx:03d}",
        "paragraph_number": idx,
        "input_text": paragraph["text"],
        "decision": analysis["decision"],
        "classification": analysis["classification"],
        "risk_level": analysis["risk_level"],
        "explanation": analysis["explanation"],
        "suggested_redline": analysis.get("suggested_redline", ""),
        "confidence": analysis.get("confidence", 0.5),
        "relevant_playbook_section": analysis.get("relevant_playbook_section", "N/A"),
        "triggered_rules": analysis.get("triggered_rules", []),
        "start_index": paragraph.get("start_index", 0),
        "end_index": paragraph.get("end_index", 0),
        # Compatibility fields for existing output/report functions
        "input_clause_id": f"para_{idx}",
        "input_clause_section": analysis.get("relevant_playbook_section", "N/A"),
        "matched_playbook_id": None,
        "matched_playbook_text": None,
        "similarity_score": 0.0,
        "match_type": "full_context_llm",
        "raw_text": paragraph["text"],
    }
