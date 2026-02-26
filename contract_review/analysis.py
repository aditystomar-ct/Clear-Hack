"""LLM analyzer, heuristic, and hybrid pipeline."""

import json

from .config import ANTHROPIC_API_KEY, LLM_MODEL
from .models import Clause, Rule


def _compute_confidence(sim: float, rules: list[tuple[Rule, float]]) -> float:
    """Compute confidence score (0.0-1.0) for heuristic analysis."""
    deviation_signal = (1 - sim) * 0.4
    avg_rule_score = sum(s for _, s in rules) / len(rules) if rules else 0.0
    rule_score_signal = avg_rule_score * 0.4
    rule_count_signal = min(len(rules) / 3, 1.0) * 0.2
    return round(min(deviation_signal + rule_score_signal + rule_count_signal, 1.0), 3)


def _build_prompt(
    inp: Clause, pb: Clause, sim: float, mt: str,
    rules: list[tuple[Rule, float]],
) -> str:
    pb_block = (
        f'MATCHED PLAYBOOK CLAUSE (ClearTax Standard):\n'
        f'"{pb.text}"\nSimilarity: {sim:.2f} ({mt} match)'
        if mt != "new_clause" else
        f'NO MATCHING PLAYBOOK CLAUSE (similarity: {sim:.2f})\n'
        f'This is a NEW obligation not in ClearTax\'s standard DPA.'
    )
    rules_block = ""
    if rules:
        rules_block = "\n\nAPPLICABLE RULES FROM INTERNAL RULEBOOK:\n"
        for r, _ in rules:
            rules_block += (
                f"\n- [{r.rule_id}] {r.clause} (Risk: {r.risk})\n"
                f"  Condition: {r.subclause}\n"
            )

    return f"""You are a legal analyst reviewing a DPA for ClearTax (Defmacro Software Pvt Ltd), the data processor.
The incoming DPA is from a customer (the data controller).

Analyze this clause and determine compliance with ClearTax's playbook and internal rules.

INCOMING CLAUSE:
"{inp.text}"

{pb_block}{rules_block}

Classify as: "compliant" / "deviation_minor" / "deviation_major" / "non_compliant"
Risk: "High" / "Medium" / "Low"
Confidence: a float 0.0-1.0 indicating how confident you are in this assessment.

Respond ONLY with this JSON (no markdown fences):
{{"classification": "...", "risk_level": "...", "explanation": "...", "suggested_redline": "...", "confidence": 0.0}}"""


_llm_client = None


def _get_llm_client():
    global _llm_client
    if _llm_client is None:
        import anthropic
        _llm_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _llm_client


def _call_llm(prompt: str) -> dict:
    client = _get_llm_client()
    resp = client.messages.create(
        model=LLM_MODEL, max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def heuristic(
    _inp: Clause, _pb: Clause, sim: float, mt: str,
    rules: list[tuple[Rule, float]],
) -> dict:
    strong_rules = [(r, s) for r, s in rules if s > 0.62]
    rule_risks = [r.risk for r, _ in strong_rules]
    max_risk = "High" if "High" in rule_risks else ("Medium" if "Medium" in rule_risks else "Low")
    rule_ids = ", ".join(r.rule_id for r, _ in strong_rules)
    confidence = _compute_confidence(sim, strong_rules)

    if mt == "strong" and not strong_rules:
        return dict(classification="compliant", risk_level="Low",
                    explanation=f"Matches ClearTax standard (sim={sim:.2f}).",
                    suggested_redline="", confidence=confidence)

    if mt == "partial" and not strong_rules:
        return dict(classification="compliant", risk_level="Low",
                    explanation=f"Partial match (sim={sim:.2f}). No policy rules triggered.",
                    suggested_redline="", confidence=confidence)

    if mt == "strong":
        return dict(classification="deviation_minor", risk_level=max_risk,
                    explanation=f"Matches standard (sim={sim:.2f}) but triggers rules: {rule_ids}.",
                    suggested_redline="", confidence=confidence)

    if mt == "partial":
        cls = "deviation_major" if max_risk == "High" else "deviation_minor"
        return dict(classification=cls, risk_level=max_risk,
                    explanation=f"Partial match (sim={sim:.2f}). Triggered: {rule_ids}.",
                    suggested_redline="", confidence=confidence)

    if not strong_rules:
        return dict(classification="compliant", risk_level="Low",
                    explanation=f"New clause (sim={sim:.2f}). No policy rules triggered.",
                    suggested_redline="", confidence=confidence)

    return dict(
        classification="deviation_major" if max_risk == "High" else "deviation_minor",
        risk_level=max_risk,
        explanation=f"New clause not in ClearTax standard (sim={sim:.2f}). Triggered: {rule_ids}.",
        suggested_redline="", confidence=confidence,
    )


def analyze_clause(inp, pb, sim, mt, rules, use_llm) -> dict:
    if use_llm:
        try:
            return _call_llm(_build_prompt(inp, pb, sim, mt, rules))
        except Exception as e:
            print(f"    LLM error: {e}. Using heuristic.")
    return heuristic(inp, pb, sim, mt, rules)


def _build_batch_prompt(items: list[tuple]) -> str:
    """Build a single prompt for analyzing multiple clauses at once."""
    clauses_block = ""
    for i, (inp, pb, sim, mt, rules) in enumerate(items, start=1):
        pb_block = (
            f'Matched playbook: "{pb.text}" (sim={sim:.2f}, {mt})'
            if mt != "new_clause" else
            f'No playbook match (sim={sim:.2f}). New obligation not in ClearTax standard.'
        )
        rules_block = ""
        if rules:
            rules_block = " | Rules: " + "; ".join(
                f"[{r.rule_id}] {r.clause} (Risk: {r.risk})"
                for r, _ in rules
            )
        clauses_block += f'\n--- CLAUSE {i} ---\n"{inp.text}"\n{pb_block}{rules_block}\n'

    return f"""You are a legal analyst reviewing a DPA for ClearTax (Defmacro Software Pvt Ltd), the data processor.
The incoming DPA is from a customer (the data controller).

Analyze each clause below for compliance with ClearTax's playbook and internal rules.

{clauses_block}

For EACH clause, classify as: "compliant" / "deviation_minor" / "deviation_major" / "non_compliant"
Risk: "High" / "Medium" / "Low"
Confidence: float 0.0-1.0

Respond ONLY with a JSON array (no markdown fences). One object per clause, in order:
[{{"clause_index": 1, "classification": "...", "risk_level": "...", "explanation": "...", "suggested_redline": "...", "confidence": 0.0}}, ...]"""


def analyze_clauses_batch(
    items: list[tuple],
    on_progress=None,
) -> list[dict]:
    """
    Analyze multiple clauses in batches of BATCH_SIZE via a single LLM call each.
    Falls back to heuristic per-clause on LLM error.
    """
    BATCH_SIZE = 5
    results: list[dict] = []
    total = len(items)

    for batch_start in range(0, total, BATCH_SIZE):
        batch = items[batch_start:batch_start + BATCH_SIZE]
        batch_end = min(batch_start + BATCH_SIZE, total)

        if on_progress:
            on_progress(batch_start, total, f"Analyzing clauses {batch_start+1}-{batch_end} of {total}...")

        try:
            client = _get_llm_client()
            prompt = _build_batch_prompt(batch)
            resp = client.messages.create(
                model=LLM_MODEL, max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            parsed = json.loads(text)

            if isinstance(parsed, list) and len(parsed) == len(batch):
                for item in parsed:
                    item.setdefault("factual_issues", False)
                    item.setdefault("factual_notes", "")
                results.extend(parsed)
            else:
                raise ValueError(f"Expected {len(batch)} results, got {len(parsed) if isinstance(parsed, list) else 'non-list'}")

        except Exception as e:
            print(f"    Batch LLM error: {e}. Falling back to heuristic for this batch.")
            for inp, pb, sim, mt, rules in batch:
                results.append(heuristic(inp, pb, sim, mt, rules))

    if on_progress:
        on_progress(total, total, f"Analysis complete ({total} clauses)")

    return results
