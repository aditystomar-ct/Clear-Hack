"""Output generation: summary, flag building, rich terminal output."""


def build_flag(idx, inp, pb, sim, mt, rules, analysis) -> dict:
    return {
        "flag_id": f"FLAG_{idx:03d}",
        "input_clause_id": inp.id,
        "input_clause_section": inp.section,
        "input_text": inp.text,
        "matched_playbook_id": pb.id if mt != "new_clause" else None,
        "matched_playbook_text": pb.text if mt != "new_clause" else None,
        "similarity_score": round(sim, 4),
        "match_type": mt,
        "triggered_rules": [
            {"rule_id": r.rule_id, "source": r.source,
             "clause": r.clause, "risk": r.risk, "match_score": round(s, 4)}
            for r, s in rules
        ],
        "classification": analysis["classification"],
        "risk_level": analysis["risk_level"],
        "explanation": analysis["explanation"],
        "suggested_redline": analysis["suggested_redline"],
        "confidence": analysis.get("confidence", 0.5),
        "start_index": inp.start_index,
        "end_index": inp.end_index,
        "raw_text": inp.raw_text,
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
        f"[bold]Model:[/bold] {metadata.get('embedding_model', 'N/A')}"
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
