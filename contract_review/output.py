"""Output generation: summary, flag building, rich terminal output."""

from difflib import SequenceMatcher


def _find_paragraph_position(clause_text: str, paragraphs: list[dict]) -> tuple[int, int]:
    """Find the best-matching paragraph for a clause and return its (start_index, end_index).

    Tries exact substring match first, then falls back to fuzzy matching.
    """
    if not paragraphs:
        return 0, 0

    if not clause_text:
        return paragraphs[0]["start_index"], paragraphs[0]["end_index"]

    # Normalize for matching
    clause_lower = clause_text.lower().strip()
    if not clause_lower:
        return paragraphs[0]["start_index"], paragraphs[0]["end_index"]

    # Try exact substring match
    for p in paragraphs:
        if clause_lower[:80] in p["text"].lower():
            return p["start_index"], p["end_index"]

    # Fuzzy match — find paragraph with highest similarity
    best_score = 0.0
    best_para = paragraphs[0]
    for p in paragraphs:
        score = SequenceMatcher(None, clause_lower[:200], p["text"].lower()[:200]).ratio()
        if score > best_score:
            best_score = score
            best_para = p

    return best_para["start_index"], best_para["end_index"]


def build_flag_from_llm(idx: int, llm_result: dict, input_paragraphs: list[dict]) -> dict:
    """Build a flag dict from LLM analysis result, mapping clause text to paragraph positions."""

    clause_text = llm_result.get("clause_text") or ""
    explanation = llm_result.get("explanation") or ""
    suggested_redline = llm_result.get("suggested_redline") or ""
    section = llm_result.get("section") or ""
    matched_pb_text = llm_result.get("matched_playbook_text") or None
    matched_pb_section = llm_result.get("matched_playbook_section") or None
    cls = llm_result.get("classification") or "compliant"
    risk = llm_result.get("risk_level") or "Low"
    confidence = llm_result.get("confidence")
    if confidence is None:
        confidence = 0.5
    triggered_rules = llm_result.get("triggered_rules") or []

    start_index, end_index = _find_paragraph_position(clause_text, input_paragraphs)

    # Determine match type
    if matched_pb_section:
        match_type = "matched"
    else:
        match_type = "new_clause"

    return {
        "flag_id": f"FLAG_{idx:03d}",
        "input_clause_id": f"clause_{idx}",
        "input_clause_section": section,
        "input_text": clause_text,
        "matched_playbook_id": None,
        "matched_playbook_text": matched_pb_text,
        "similarity_score": None,
        "match_type": match_type,
        "triggered_rules": triggered_rules,
        "classification": cls,
        "risk_level": risk,
        "explanation": explanation,
        "suggested_redline": suggested_redline,
        "confidence": confidence,
        "start_index": start_index,
        "end_index": end_index,
        "raw_text": clause_text[:200],
    }


def generate_summary(flags):
    by_cls = {}
    by_risk = {}
    for f in flags:
        by_cls[f["classification"]] = by_cls.get(f["classification"], 0) + 1
        by_risk[f["risk_level"]] = by_risk.get(f["risk_level"], 0) + 1

    ranked = sorted(flags, key=lambda x: (
        {"High": 0, "Medium": 1, "Low": 2}.get(x["risk_level"], 9),
        {"non_compliant": 0, "deviation_major": 1, "deviation_minor": 2, "compliant": 3}.get(x["classification"], 9),
    ))
    return {
        "total_clauses_analyzed": len(flags),
        "classification_breakdown": by_cls,
        "risk_breakdown": by_risk,
        "high_risk_count": sum(1 for f in flags if f["risk_level"] == "High"),
        "non_compliant_count": sum(1 for f in flags if f["classification"] == "non_compliant"),
        "top_risks": [
            {"flag_id": f["flag_id"], "section": f["input_clause_section"],
             "risk": f["risk_level"], "classification": f["classification"],
             "summary": f["explanation"][:200]}
            for f in ranked[:10]
        ],
    }



def print_rich_summary(summary: dict, flags: list[dict], metadata: dict) -> None:
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich import box
    except ImportError:
        return _print_plain_summary(summary, flags)

    console = Console()
    console.print()
    risk_bd = summary.get("risk_breakdown", {})
    cls_bd = summary.get("classification_breakdown", {})
    summary_text = (
        f"[bold]Clauses Analyzed:[/bold] {summary['total_clauses_analyzed']}\n"
        f"[bold red]High Risk:[/bold red] {risk_bd.get('High', 0)}  "
        f"[bold yellow]Medium:[/bold yellow] {risk_bd.get('Medium', 0)}  "
        f"[bold green]Low:[/bold green] {risk_bd.get('Low', 0)}\n"
        f"[bold]Compliant:[/bold] {cls_bd.get('compliant', 0)}  "
        f"[bold yellow]Minor Dev:[/bold yellow] {cls_bd.get('deviation_minor', 0)}  "
        f"[bold red]Major Dev:[/bold red] {cls_bd.get('deviation_major', 0)}  "
        f"[bold]Non-Compliant:[/bold] {cls_bd.get('non_compliant', 0)}\n"
        f"[bold]Mode:[/bold] {metadata.get('analysis_mode', 'N/A')}  "
        f"[bold]Model:[/bold] {metadata.get('llm_model', 'N/A')}"
    )
    console.print(Panel(summary_text, title="DPA Review Summary", border_style="blue", expand=False))

    table = Table(title="Top Risk Flags", box=box.ROUNDED, show_lines=True)
    table.add_column("Flag", style="bold", width=10)
    table.add_column("Section", width=25)
    table.add_column("Risk", width=8)
    table.add_column("Classification", width=18)
    table.add_column("Confidence", width=10)
    table.add_column("Summary", width=60)
    risk_style = {"High": "bold red", "Medium": "bold yellow", "Low": "bold green"}
    ranked = sorted(flags, key=lambda x: (
        {"High": 0, "Medium": 1, "Low": 2}.get(x["risk_level"], 9),
        {"non_compliant": 0, "deviation_major": 1, "deviation_minor": 2, "compliant": 3}.get(x["classification"], 9),
    ))
    for f in ranked[:10]:
        if f["classification"] == "compliant":
            continue
        table.add_row(
            f["flag_id"], f.get("input_clause_section", "") or "N/A",
            f"[{risk_style.get(f['risk_level'], '')}]{f['risk_level']}[/]",
            f["classification"].replace("_", " ").title(),
            f'{f.get("confidence", 0) * 100:.0f}%',
            f["explanation"][:80] + "..." if len(f["explanation"]) > 80 else f["explanation"],
        )
    console.print(table)
    console.print()


def _print_plain_summary(summary: dict, flags: list[dict]) -> None:
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Clauses analysed : {summary['total_clauses_analyzed']}")
    print(f"  Classification   : {summary['classification_breakdown']}")
    print(f"  Risk breakdown   : {summary['risk_breakdown']}")
    print(f"  High-risk flags  : {summary['high_risk_count']}")
    print(f"  Non-compliant    : {summary['non_compliant_count']}")
    if summary["top_risks"]:
        print(f"\n  TOP RISKS:")
        for r in summary["top_risks"][:5]:
            print(f"    [{r['risk']:6s}] {r['flag_id']} ({r['section'] or 'N/A'}): {r['classification']}")
    print()
