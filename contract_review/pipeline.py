"""Main orchestration pipeline — embedding-based matching with heuristic/LLM/hybrid analysis."""

from pathlib import Path

from .config import (
    ANTHROPIC_API_KEY, LLM_MODEL,
    PLAYBOOK_PATH, RULEBOOK_PATH, EMBED_MODEL,
)
from .models import Clause
from .extractors import (
    extract_doc_id, fetch_gdoc_paragraphs, fetch_docx_paragraphs,
    load_rulebook, extract_clauses,
)
from .matching import (
    match_clauses, match_all_rules, apply_rule_specificity, get_active_model_name,
)
from .analysis import analyze_clause, analyze_clauses_batch, heuristic, _compute_confidence
from .output import build_flag, generate_summary, print_rich_summary
from .database import save_review
from .notifications import send_slack_notification


def run_pipeline(
    input_source: str,
    playbook_source: str | None = None,
    analysis_mode: str = "hybrid",
    reviewer: str = "",
    progress_callback=None,
    send_notification: bool = False,
    streamlit_url: str = "http://localhost:8501",
) -> dict:
    """
    Run the full DPA review pipeline with embedding-based matching.

    Supports heuristic, llm, and hybrid analysis modes.
    Returns a dict with metadata, summary, flags, and review_id.
    """
    BASE_DIR = Path(__file__).parent.parent

    def progress(step, total, msg):
        if progress_callback:
            progress_callback(step, total, msg)
        else:
            print(msg)

    # Determine input type
    input_is_local = Path(input_source).suffix in (".docx", ".doc") or (
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
    has_llm = bool(ANTHROPIC_API_KEY)
    if analysis_mode in ("llm", "hybrid") and not has_llm:
        print(f"Warning: --mode {analysis_mode} requested but ANTHROPIC_API_KEY not set. Falling back to heuristic.")
        analysis_mode = "heuristic"

    mode_display = {
        "heuristic": "Heuristic only",
        "llm": f"LLM ({LLM_MODEL})",
        "hybrid": f"Hybrid (heuristic + LLM for flagged clauses)",
    }.get(analysis_mode, analysis_mode)

    print(f"DPA Contract Review Tool")
    print(f"Analysis mode: {mode_display}")
    print(f"Input: {input_doc_id or input_path}")
    print()

    import time as _time
    _t0 = _time.time()

    # Step 1: Load rulebook
    progress(1, 7, "[Step 1/7] Loading rulebook...")
    rules = load_rulebook(RULEBOOK_PATH)
    print(f"  Loaded {len(rules)} rules ({sum(1 for r in rules if r.source == 'legal')} legal, "
          f"{sum(1 for r in rules if r.source == 'infosec')} infosec)")

    # Step 2: Fetch paragraphs
    progress(2, 7, "[Step 2/7] Fetching paragraphs...")
    if input_doc_id:
        input_paras = fetch_gdoc_paragraphs(input_doc_id)
    else:
        input_paras = fetch_docx_paragraphs(input_path)
    print(f"  Input: {len(input_paras)} paragraphs")

    pb_path = Path(playbook_source) if playbook_source else PLAYBOOK_PATH
    if playbook_source and not pb_path.exists():
        pb_id = extract_doc_id(playbook_source)
        pb_paras = fetch_gdoc_paragraphs(pb_id)
    else:
        pb_paras = fetch_docx_paragraphs(pb_path)
    print(f"  Playbook: {len(pb_paras)} paragraphs")

    # Step 3: Extract clauses
    progress(3, 7, "[Step 3/7] Extracting clauses...")
    input_clauses = extract_clauses(input_paras, "input")
    playbook_clauses = extract_clauses(pb_paras, "playbook")
    print(f"  Input clauses:    {len(input_clauses)}")
    print(f"  Playbook clauses: {len(playbook_clauses)}")

    if not input_clauses:
        raise ValueError("No clauses extracted from input.")
    if not playbook_clauses:
        raise ValueError("No clauses extracted from playbook.")

    # Step 4: Match clauses + rules
    progress(4, 7, "[Step 4/7] Matching clauses...")
    matches = match_clauses(input_clauses, playbook_clauses)
    strong = sum(1 for *_, mt in matches if mt == "strong")
    partial = sum(1 for *_, mt in matches if mt == "partial")
    new = sum(1 for *_, mt in matches if mt == "new_clause")
    print(f"  Strong: {strong}  |  Partial: {partial}  |  New: {new}")

    clause_rules_raw = match_all_rules([inp for inp, _, _, _ in matches], rules)
    clause_rules = apply_rule_specificity(clause_rules_raw)
    triggered = sum(1 for cr in clause_rules if cr)
    print(f"  Clauses with triggered rules: {triggered}/{len(matches)}")

    # Step 5: Analyse clauses (batched LLM for speed)
    progress(5, 7, "[Step 5/7] Analysing clauses...")
    flags: list[dict] = []
    total = len(matches)
    llm_calls = 0

    if analysis_mode == "heuristic":
        for n, ((inp, pb, sim, mt), crules) in enumerate(
            zip(matches, clause_rules), start=1,
        ):
            if mt == "strong" and not crules:
                analysis = dict(
                    classification="compliant", risk_level="Low",
                    explanation=f"Matches ClearTax standard (sim={sim:.2f}).",
                    suggested_redline="", confidence=_compute_confidence(sim, crules),
                )
            else:
                analysis = heuristic(inp, pb, sim, mt, crules)
            flags.append(build_flag(n, inp, pb, sim, mt, crules, analysis))

    elif analysis_mode == "llm":
        llm_items = [(inp, pb, sim, mt, crules)
                      for (inp, pb, sim, mt), crules in zip(matches, clause_rules)]

        def on_llm_progress(done, batch_total, msg):
            frac = 5 / 7 + (done / batch_total) * (1 / 7) if batch_total > 0 else 5 / 7
            progress(frac * 7, 7, f"[Step 5/7] {msg}")

        batch_results = analyze_clauses_batch(llm_items, on_progress=on_llm_progress)
        llm_calls = total
        for n, (((inp, pb, sim, mt), crules), analysis) in enumerate(
            zip(zip(matches, clause_rules), batch_results), start=1,
        ):
            flags.append(build_flag(n, inp, pb, sim, mt, crules, analysis))

    else:
        heuristic_results = {}
        llm_indices = []

        for n, ((inp, pb, sim, mt), crules) in enumerate(
            zip(matches, clause_rules),
        ):
            h = heuristic(inp, pb, sim, mt, crules)
            if h["classification"] == "compliant" and not crules:
                heuristic_results[n] = h
            else:
                llm_indices.append(n)

        print(f"  Heuristic pass: {len(heuristic_results)} compliant, {len(llm_indices)} need LLM")

        llm_items = []
        for idx in llm_indices:
            inp, pb, sim, mt = matches[idx]
            crules = clause_rules[idx]
            llm_items.append((inp, pb, sim, mt, crules))

        llm_results_map = {}
        if llm_items:
            def on_llm_progress(done, batch_total, msg):
                frac = 5 / 7 + (done / batch_total) * (1 / 7) if batch_total > 0 else 5 / 7
                progress(frac * 7, 7, f"[Step 5/7] {msg}")

            batch_results = analyze_clauses_batch(llm_items, on_progress=on_llm_progress)
            llm_calls = len(llm_items)
            for i, idx in enumerate(llm_indices):
                llm_results_map[idx] = batch_results[i]

        for n in range(len(matches)):
            inp, pb, sim, mt = matches[n]
            crules = clause_rules[n]
            analysis = heuristic_results.get(n) or llm_results_map.get(n)
            flags.append(build_flag(n + 1, inp, pb, sim, mt, crules, analysis))

    if analysis_mode != "heuristic":
        print(f"  LLM batches: {(llm_calls + 4) // 5} calls for {llm_calls} clauses (5 per batch)")

    # Step 6: Google Doc comments + highlights
    summary = generate_summary(flags)

    embedding_model = get_active_model_name()
    elapsed = round(_time.time() - _t0, 1)
    output_metadata = {
        "tool": "DPA Contract Review Tool",
        "input_source": input_doc_id or str(input_path.name),
        "playbook_source": playbook_source or PLAYBOOK_PATH.name,
        "rulebook": RULEBOOK_PATH.name,
        "rules_loaded": len(rules),
        "analysis_mode": analysis_mode,
        "embedding_model": embedding_model,
        "llm_calls": llm_calls,
        "elapsed_seconds": elapsed,
    }

    progress(6, 7, "[Step 6/7] Review flags before publishing to Google Doc...")

    # Step 7: Save to database
    progress(7, 7, "[Step 7/7] Saving review...")
    contract_name = input_doc_id or input_path.name
    review_id = save_review(
        contract_name=contract_name,
        analysis_mode=analysis_mode,
        summary=summary,
        metadata=output_metadata,
        flags=flags,
        reviewer=reviewer,
    )

    if send_notification:
        send_slack_notification(contract_name, summary, review_id, streamlit_url)

    elapsed_final = round(_time.time() - _t0, 1)
    print(f"\n  Done in {elapsed_final}s ({llm_calls} clauses via LLM in {(llm_calls + 4) // 5} batches)")
    print_rich_summary(summary, flags, output_metadata)

    return {
        "metadata": output_metadata,
        "summary": summary,
        "flags": flags,
        "review_id": review_id,
    }
