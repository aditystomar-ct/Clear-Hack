"""Output generation: flags.json, HTML report, rich terminal output."""

import json
import html as html_mod

from .config import OUTPUT_DIR


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


def generate_html_report(flags: list[dict], summary: dict, metadata: dict) -> str:
    """Generate a self-contained interactive HTML report."""
    risk_colors = {"High": "#e74c3c", "Medium": "#f39c12", "Low": "#27ae60"}
    cls_colors = {
        "non_compliant": "#c0392b", "deviation_major": "#e74c3c",
        "deviation_minor": "#f39c12", "compliant": "#27ae60",
    }

    rows_html = ""
    for f in flags:
        risk_badge = f'<span class="badge" style="background:{risk_colors.get(f["risk_level"], "#999")}">{f["risk_level"]}</span>'
        cls_badge = f'<span class="badge" style="background:{cls_colors.get(f["classification"], "#999")}">{f["classification"].replace("_", " ").title()}</span>'
        confidence_pct = f'{f.get("confidence", 0) * 100:.0f}%'

        rules_html = ""
        if f.get("triggered_rules"):
            rules_html = "<ul>" + "".join(
                f'<li>[{r["source"].upper()}] {html_mod.escape(r["clause"])} (Risk: {r["risk"]})</li>'
                for r in f["triggered_rules"]
            ) + "</ul>"

        pb_text = html_mod.escape(f.get("matched_playbook_text") or "No playbook match")
        inp_text = html_mod.escape(f["input_text"])
        redline = html_mod.escape(f.get("suggested_redline") or "None")
        explanation = html_mod.escape(f["explanation"])

        rows_html += f"""
        <tr class="flag-row" data-risk="{f['risk_level']}" data-cls="{f['classification']}">
            <td>{f['flag_id']}</td>
            <td>{html_mod.escape(f.get('input_clause_section', '') or 'N/A')}</td>
            <td>{risk_badge}</td>
            <td>{cls_badge}</td>
            <td>{confidence_pct}</td>
            <td>{f.get('similarity_score', 0):.2f} ({f.get('match_type', 'N/A')})</td>
            <td><button class="expand-btn" onclick="toggleRow(this)">+</button></td>
        </tr>
        <tr class="detail-row" style="display:none">
            <td colspan="7">
                <div class="detail-grid">
                    <div class="detail-col"><h4>Incoming Clause</h4><p class="clause-text">{inp_text}</p></div>
                    <div class="detail-col"><h4>Playbook Clause</h4><p class="clause-text">{pb_text}</p></div>
                </div>
                <div class="detail-section"><h4>Explanation</h4><p>{explanation}</p></div>
                <div class="detail-section"><h4>Triggered Rules</h4>{rules_html or '<p>None</p>'}</div>
                <div class="detail-section"><h4>Suggested Redline</h4><p class="redline">{redline}</p></div>
            </td>
        </tr>"""

    risk_bd = summary.get("risk_breakdown", {})
    cls_bd = summary.get("classification_breakdown", {})

    report = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DPA Contract Review Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f6fa;color:#2c3e50;padding:20px}}.container{{max-width:1200px;margin:0 auto}}h1{{font-size:1.8em;margin-bottom:5px}}.subtitle{{color:#7f8c8d;margin-bottom:20px}}.summary-cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:15px;margin-bottom:25px}}.card{{background:white;border-radius:10px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.08);text-align:center}}.card .number{{font-size:2.2em;font-weight:700}}.card .label{{color:#7f8c8d;font-size:0.85em;margin-top:5px}}.charts{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:25px}}.chart-box{{background:white;border-radius:10px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}.chart-box canvas{{max-height:250px}}.filters{{margin-bottom:15px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}}.filters select,.filters input{{padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:0.9em}}table{{width:100%;border-collapse:collapse;background:white;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}th{{background:#34495e;color:white;padding:12px 15px;text-align:left;cursor:pointer}}td{{padding:12px 15px;border-bottom:1px solid #ecf0f1}}.flag-row:hover{{background:#f8f9fa}}.badge{{padding:4px 10px;border-radius:12px;color:white;font-size:0.8em;font-weight:600}}.expand-btn{{background:#3498db;color:white;border:none;border-radius:50%;width:28px;height:28px;cursor:pointer;font-size:1.1em}}.detail-row td{{background:#f8f9fa;padding:20px}}.detail-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:15px}}.detail-col{{background:white;border-radius:8px;padding:15px;border:1px solid #e0e0e0}}.detail-col h4{{color:#2c3e50;margin-bottom:8px}}.clause-text{{font-size:0.9em;line-height:1.6;color:#555}}.detail-section{{margin-top:12px}}.detail-section h4{{color:#2c3e50;margin-bottom:5px}}.redline{{background:#fff3cd;padding:10px;border-radius:6px;border-left:3px solid #f39c12;font-style:italic}}.print-btn{{background:#2c3e50;color:white;border:none;padding:10px 20px;border-radius:6px;cursor:pointer}}@media print{{.filters,.print-btn,.expand-btn{{display:none}}.detail-row{{display:table-row!important}}}}
</style></head><body><div class="container">
<h1>DPA Contract Review Report</h1>
<p class="subtitle">Mode: {html_mod.escape(metadata.get('analysis_mode','N/A'))} | Model: {html_mod.escape(metadata.get('embedding_model','N/A'))}</p>
<div class="summary-cards">
<div class="card"><div class="number">{summary.get('total_clauses_analyzed',len(flags))}</div><div class="label">Clauses Analyzed</div></div>
<div class="card"><div class="number" style="color:#e74c3c">{summary['high_risk_count']}</div><div class="label">High Risk</div></div>
<div class="card"><div class="number" style="color:#c0392b">{summary['non_compliant_count']}</div><div class="label">Non-Compliant</div></div>
<div class="card"><div class="number" style="color:#27ae60">{cls_bd.get('compliant',0)}</div><div class="label">Compliant</div></div>
</div>
<div class="charts"><div class="chart-box"><canvas id="riskChart"></canvas></div><div class="chart-box"><canvas id="clsChart"></canvas></div></div>
<div class="filters">
<select id="filterRisk" onchange="filterTable()"><option value="">All Risks</option><option value="High">High</option><option value="Medium">Medium</option><option value="Low">Low</option></select>
<select id="filterCls" onchange="filterTable()"><option value="">All Classifications</option><option value="compliant">Compliant</option><option value="deviation_minor">Deviation Minor</option><option value="deviation_major">Deviation Major</option><option value="non_compliant">Non-Compliant</option></select>
<input type="text" id="filterSearch" placeholder="Search..." oninput="filterTable()">
<button class="print-btn" onclick="window.print()">Export PDF</button></div>
<table><thead><tr><th>Flag ID</th><th>Section</th><th>Risk</th><th>Classification</th><th>Confidence</th><th>Similarity</th><th>Details</th></tr></thead>
<tbody id="flagsBody">{rows_html}</tbody></table></div>
<script>
function toggleRow(btn){{const d=btn.closest('tr').nextElementSibling;const h=d.style.display==='none';d.style.display=h?'table-row':'none';btn.textContent=h?'-':'+'}}
function filterTable(){{const r=document.getElementById('filterRisk').value;const c=document.getElementById('filterCls').value;const s=document.getElementById('filterSearch').value.toLowerCase();document.querySelectorAll('.flag-row').forEach(row=>{{const detail=row.nextElementSibling;const show=(!r||row.dataset.risk===r)&&(!c||row.dataset.cls===c)&&(!s||row.textContent.toLowerCase().includes(s)||detail.textContent.toLowerCase().includes(s));row.style.display=show?'':'none';if(!show)detail.style.display='none'}})}}
new Chart(document.getElementById('riskChart'),{{type:'doughnut',data:{{labels:{json.dumps(list(risk_bd.keys()))},datasets:[{{data:{json.dumps(list(risk_bd.values()))},backgroundColor:{json.dumps([risk_colors.get(k,'#999') for k in risk_bd.keys()])}}}]}},options:{{responsive:true,plugins:{{title:{{display:true,text:'Risk Breakdown'}}}}}}}});
new Chart(document.getElementById('clsChart'),{{type:'doughnut',data:{{labels:{json.dumps([k.replace('_',' ').title() for k in cls_bd.keys()])},datasets:[{{data:{json.dumps(list(cls_bd.values()))},backgroundColor:{json.dumps([cls_colors.get(k,'#999') for k in cls_bd.keys()])}}}]}},options:{{responsive:true,plugins:{{title:{{display:true,text:'Classification Breakdown'}}}}}}}});
</script></body></html>"""

    report_path = OUTPUT_DIR / "report.html"
    with open(report_path, "w") as f:
        f.write(report)
    return str(report_path)


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
