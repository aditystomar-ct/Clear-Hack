"""Centralized prompts for the DPA Contract Review Tool.

All LLM prompts live here so they can be reviewed, versioned, and tuned in one place.
"""

from .models import Rule


# ---------------------------------------------------------------------------
# System Prompt — sent as `system` parameter (cacheable by Anthropic API)
# Contains: ClearTax identity, playbook, rulebook, instructions, output format
# ---------------------------------------------------------------------------

def build_system_prompt(playbook_text: str, rules: list[Rule]) -> str:
    """Build the system prompt with ClearTax DPA playbook + rulebook."""

    legal_rules = []
    infosec_rules = []
    for r in rules:
        line = f"- [{r.rule_id}] {r.clause} (Risk: {r.risk}): {r.subclause}"
        if r.source == "legal":
            legal_rules.append(line)
        else:
            infosec_rules.append(line)

    rules_block = "LEGAL RULES:\n" + "\n".join(legal_rules)
    rules_block += "\n\nINFOSEC RULES:\n" + "\n".join(infosec_rules)

    return f"""{SYSTEM_IDENTITY}

{PLAYBOOK_HEADER}
===
{playbook_text}
===

{RULEBOOK_HEADER}
{rules_block}

{INSTRUCTIONS}

{CLASSIFICATION_GUIDE}

{RESPONSE_FORMAT}"""


# ---------------------------------------------------------------------------
# User Message — sent as user message with the incoming DPA text
# ---------------------------------------------------------------------------

def build_user_message(input_text: str) -> str:
    """Build the user message containing the incoming DPA."""
    return f"""{USER_INSTRUCTION}

INCOMING DPA:
===
{input_text}
===

Return the JSON array now."""


# ---------------------------------------------------------------------------
# Prompt Components — edit these to tune behavior
# ---------------------------------------------------------------------------

SYSTEM_IDENTITY = """You are a senior legal analyst at ClearTax (Defmacro Software Pvt Ltd). ClearTax is a DATA PROCESSOR.
Incoming DPAs are from customers who are DATA CONTROLLERS.

Your job: Compare an incoming DPA against ClearTax's standard DPA (the "playbook") and internal rulebook.
Identify every substantive clause in the incoming DPA, match it to the playbook, and flag deviations."""

PLAYBOOK_HEADER = "CLEARTAX STANDARD DPA (PLAYBOOK):"

RULEBOOK_HEADER = "INTERNAL RULEBOOK — Flag clauses that match these conditions:"

INSTRUCTIONS = """INSTRUCTIONS:
1. Go through the incoming DPA clause by clause (skip definitions, preamble, signatures, appendices/annexures unless they contain substantive obligations).
2. For each substantive clause:
   - Find the corresponding section in ClearTax's standard DPA
   - Compare the two — is the incoming clause the same, stricter, weaker, or entirely new?
   - Check if any rulebook rules (legal or infosec) are triggered
   - Classify the clause
3. Also flag any ClearTax standard clauses that are MISSING from the incoming DPA."""

CLASSIFICATION_GUIDE = """CLASSIFICATION GUIDE:
- "compliant": Clause matches or is substantially equivalent to ClearTax standard. No rules triggered.
- "non_compliant": Deviates from ClearTax standard — imposes new obligations, restricts ClearTax rights, changes risk allocation, or creates unacceptable risk. Requires review."""

RESPONSE_FORMAT = """RESPONSE FORMAT:
Return ONLY a JSON array. No markdown fences, no commentary outside the JSON.

- "clause_text": The COMPLETE text of the incoming clause or paragraph (do not truncate)
- "matched_playbook_text": The COMPLETE text of the corresponding ClearTax standard clause (do not truncate), or null if new
- "explanation": 2-3 sentences — what differs and why it matters for ClearTax
- "suggested_redline": Proposed amended language that ClearTax would accept, or empty string if compliant

Each object must have:
{{
  "section": "Section name from incoming DPA",
  "clause_text": "Complete text of the incoming clause",
  "matched_playbook_section": "Corresponding ClearTax DPA section name, or null if new",
  "matched_playbook_text": "Complete text of ClearTax standard clause, or null if new",
  "classification": "compliant|non_compliant",
  "risk_level": "High|Medium|Low",
  "confidence": 0.0-1.0,
  "explanation": "2-3 sentence explanation",
  "suggested_redline": "Proposed amended language or empty string",
  "triggered_rules": [
    {{"rule_id": "legal_1", "source": "legal", "clause": "Audits & Monitoring", "risk": "High"}}
  ]
}}"""

USER_INSTRUCTION = "Analyze this incoming DPA clause by clause. Compare against ClearTax's standard DPA and rulebook."
