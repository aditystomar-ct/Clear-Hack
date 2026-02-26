"""Main orchestration pipeline — direct LLM comparison."""

from pathlib import Path

from .config import (
    ANTHROPIC_API_KEY, LLM_MODEL,
    PLAYBOOK_PATH, RULEBOOK_PATH,
)
from .extractors import (
    extract_doc_id, fetch_gdoc_paragraphs, fetch_docx_paragraphs,
    fetch_md_paragraphs, load_rulebook,
)
from .analysis import analyze_dpa
from .output import build_flag_from_llm, generate_summary, print_rich_summary
from .database import save_review
from .notifications import send_slack_notification


def run_pipeline(
    input_source: str,
    playbook_source: str | None = None,
    reviewer: str = "",
    progress_callback=None,
    send_notification: bool = False,
    streamlit_url: str = "http://localhost:8501",
) -> dict:
    """
    Run the full DPA review pipeline with direct LLM comparison.

    Sends the full ClearTax DPA + rulebook + incoming DPA to Claude in one call.
    Returns a dict with metadata, summary, flags, and review_id.
    """
    BASE_DIR = Path(__file__).parent.parent

    def progress(step, total, msg):
        if progress_callback:
            progress_callback(step, total, msg)
        else:
            print(msg)

    # Determine input type
    input_is_local = Path(input_source).suffix in (".docx", ".doc", ".md") or (
        BASE_DIR / input_source
    ).exists()
    input_doc_id = None
    input_path = None

    if input_is_local:
        input_path = Path(input_source)
        if not input_path.is_absolute():
            input_path = BASE_DIR / input_path
        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")
    else:
        input_doc_id = extract_doc_id(input_source)

    # LLM availability check
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set. Direct LLM analysis requires an API key.")

    print(f"DPA Contract Review Tool")
    print(f"Analysis: Direct LLM ({LLM_MODEL})")
    print(f"Input: {input_doc_id or input_path}")
    print()

    import time as _time
    _t0 = _time.time()

    # Step 1: Load rulebook
    progress(1, 5, "[Step 1/5] Loading rulebook...")
    rules = load_rulebook(RULEBOOK_PATH)
    print(f"  Loaded {len(rules)} rules ({sum(1 for r in rules if r.source == 'legal')} legal, "
          f"{sum(1 for r in rules if r.source == 'infosec')} infosec)")

    # Step 2: Fetch input paragraphs + playbook text
    progress(2, 5, "[Step 2/5] Fetching documents...")
    input_doc_title = ""
    if input_doc_id:
        input_paras, input_doc_title = fetch_gdoc_paragraphs(input_doc_id)
    elif str(input_path).endswith(".md"):
        input_paras = fetch_md_paragraphs(input_path)
    else:
        input_paras = fetch_docx_paragraphs(input_path)
    print(f"  Input: {len(input_paras)} paragraphs")

    # Build full input text for LLM
    input_full_text = "\n\n".join(p["text"] for p in input_paras)

    # Load playbook text
    pb_path = Path(playbook_source) if playbook_source else PLAYBOOK_PATH
    if playbook_source and not pb_path.exists():
        pb_id = extract_doc_id(playbook_source)
        pb_paras, _ = fetch_gdoc_paragraphs(pb_id)
        playbook_text = "\n\n".join(p["text"] for p in pb_paras)
    elif str(pb_path).endswith(".md"):
        playbook_text = pb_path.read_text(encoding="utf-8")
    else:
        pb_paras = fetch_docx_paragraphs(pb_path)
        playbook_text = "\n\n".join(p["text"] for p in pb_paras)
    print(f"  Playbook: {pb_path.name}")

    # Step 3: LLM analysis — single call with full context
    progress(3, 5, "[Step 3/5] Analyzing with Claude (full document comparison)...")

    def on_llm_progress(step, total, msg):
        frac = 3 / 5 + (step / total) * (1 / 5) if total > 0 else 3 / 5
        progress(frac * 5, 5, f"[Step 3/5] {msg}")

    llm_results = analyze_dpa(
        input_text=input_full_text,
        playbook_text=playbook_text,
        rules=rules,
        on_progress=on_llm_progress,
    )
    print(f"  Claude identified {len(llm_results)} clauses")

    # Step 4: Build flags with position mapping
    progress(4, 5, "[Step 4/5] Building flags...")
    flags: list[dict] = []
    for idx, result in enumerate(llm_results, start=1):
        flag = build_flag_from_llm(idx, result, input_paras)
        flags.append(flag)

    # Count stats
    non_compliant = sum(1 for f in flags if f["classification"] != "compliant")
    high_risk = sum(1 for f in flags if f["risk_level"] == "High")
    print(f"  Flags: {len(flags)} total, {non_compliant} non-compliant, {high_risk} high risk")

    summary = generate_summary(flags)

    # Use actual document title for display
    contract_display_name = input_doc_title or (input_path.name if input_path else input_doc_id)

    elapsed = round(_time.time() - _t0, 1)
    output_metadata = {
        "tool": "DPA Contract Review Tool",
        "input_source": input_doc_id or str(input_path.name),
        "contract_name": contract_display_name,
        "playbook_source": playbook_source or PLAYBOOK_PATH.name,
        "rulebook": RULEBOOK_PATH.name,
        "rules_loaded": len(rules),
        "analysis_mode": "llm",
        "llm_model": LLM_MODEL,
        "elapsed_seconds": elapsed,
    }

    progress(4.5, 5, "[Step 4/5] Review flags before publishing to Google Doc...")

    # Step 5: Save to database
    progress(5, 5, "[Step 5/5] Saving review...")
    contract_name = contract_display_name
    review_id = save_review(
        contract_name=contract_name,
        analysis_mode="llm",
        summary=summary,
        metadata=output_metadata,
        flags=flags,
        reviewer=reviewer,
    )

    if send_notification:
        send_slack_notification(contract_name, summary, review_id, streamlit_url)

    elapsed_final = round(_time.time() - _t0, 1)
    print(f"\n  Done in {elapsed_final}s (1 LLM call, {len(flags)} clauses)")
    print_rich_summary(summary, flags, output_metadata)

    return {
        "metadata": output_metadata,
        "summary": summary,
        "flags": flags,
        "review_id": review_id,
    }
