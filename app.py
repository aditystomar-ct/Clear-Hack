"""Streamlit Web App for DPA Contract Review Tool."""

import json
import os
import tempfile
from pathlib import Path

import streamlit as st

# Load .env
BASE_DIR = Path(__file__).parent
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip("\"'"))

from contract_review.database import (
    get_review, list_reviews, get_review_flags,
    update_flag_action, bulk_update_flags, get_review_stats,
    get_rule_effectiveness,
)
from contract_review.config import ANTHROPIC_API_KEY, PLAYBOOK_PATH

st.set_page_config(
    page_title="DPA Contract Review",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .badge { padding: 4px 12px; border-radius: 12px; color: white; font-size: 0.85em; font-weight: 600; display: inline-block; }
    .high-badge { background: #e74c3c; }
    .medium-badge { background: #f39c12; }
    .low-badge { background: #27ae60; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
page = st.sidebar.radio("Navigation", ["Upload & Analyze", "Review Dashboard", "History"])
st.sidebar.markdown("---")
st.sidebar.markdown("**DPA Contract Review Tool**")
st.sidebar.caption(f"LLM: {'Available' if ANTHROPIC_API_KEY else 'Not configured'}")

# Team view filter (applies to Review Dashboard)
team_view = st.sidebar.radio("Team View", ["All", "Legal", "Infosec"])
st.sidebar.caption("Filter flags by rule source for team-specific reviews.")


# ---------------------------------------------------------------------------
# PAGE 1: UPLOAD & ANALYZE
# ---------------------------------------------------------------------------
if page == "Upload & Analyze":
    st.title("Upload & Analyze DPA")
    st.markdown("Compare an incoming DPA against ClearTax's playbook and internal rulebook using embedding-based matching.")

    col1, col2 = st.columns(2)

    with col1:
        input_method = st.radio("Input Method", ["Upload .docx file", "Google Doc URL"])
        uploaded_file = None
        gdoc_url = ""
        if input_method == "Upload .docx file":
            uploaded_file = st.file_uploader("Upload DPA document", type=["docx"])
        else:
            gdoc_url = st.text_input("Google Doc URL or ID")

    with col2:
        analysis_mode = st.selectbox("Analysis Mode", ["hybrid", "llm", "heuristic"], index=0)
        st.caption({
            "hybrid": "Heuristic first, LLM only for flagged/uncertain clauses (~60% cost savings).",
            "llm": "Send every clause to Claude for analysis (most accurate, highest cost).",
            "heuristic": "Rule-based analysis only, no LLM calls (fastest, lowest cost).",
        }[analysis_mode])

        reviewer_name = st.text_input("Reviewer Name", placeholder="Your name (optional)")

        playbook_option = st.selectbox("Playbook", ["ClearTax DPA (default)", "Custom Google Doc"])
        custom_playbook = None
        if playbook_option != "ClearTax DPA (default)":
            custom_playbook = st.text_input("Custom playbook Google Doc URL or ID")

    if analysis_mode in ("hybrid", "llm") and not ANTHROPIC_API_KEY:
        st.warning("ANTHROPIC_API_KEY not set in .env. LLM modes will fall back to heuristic.")

    st.markdown("---")

    if st.button("Analyze DPA", type="primary", use_container_width=True):
        if input_method == "Upload .docx file" and uploaded_file is None:
            st.error("Please upload a .docx file.")
            st.stop()
        if input_method == "Google Doc URL" and not gdoc_url.strip():
            st.error("Please enter a Google Doc URL or ID.")
            st.stop()

        # Save uploaded file to temp dir
        if uploaded_file:
            tmp_dir = tempfile.mkdtemp()
            tmp_path = os.path.join(tmp_dir, uploaded_file.name)
            with open(tmp_path, "wb") as f:
                f.write(uploaded_file.read())
            input_source = tmp_path
        else:
            input_source = gdoc_url.strip()

        progress_bar = st.progress(0, text="Starting analysis...")
        status_text = st.empty()
        log_area = st.empty()
        log_lines = []

        def progress_callback(step, total, msg):
            pct = min(step / total, 1.0) if total > 0 else 0
            progress_bar.progress(pct, text=msg)
            status_text.markdown(f"**{msg}**")
            log_lines.append(msg)
            log_area.code("\n".join(log_lines[-15:]), language="text")

        try:
            from contract_review.pipeline import run_pipeline
            result = run_pipeline(
                input_source=input_source,
                analysis_mode="hybrid",
                progress_callback=progress_callback,
                add_google_comments=True,
            )

            progress_bar.progress(1.0, text="Analysis complete!")
            status_text.empty()
            log_area.empty()
            st.success(f"Analysis complete! Review ID: #{result['review_id']} ({result['metadata'].get('elapsed_seconds', '?')}s)")
            st.session_state["current_review_id"] = result["review_id"]

            # Summary metrics
            summary = result["summary"]
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Clauses Analyzed", summary["total_clauses_analyzed"])
            c2.metric("High Risk", summary["high_risk_count"])
            c3.metric("Non-Compliant", summary["non_compliant_count"])
            c4.metric("Compliant", summary.get("classification_breakdown", {}).get("compliant", 0))
            c5.metric("LLM Batches", f"{(result['metadata'].get('llm_calls', 0) + 4) // 5}")

            st.info("Go to **Review Dashboard** in the sidebar to review flags in detail.")

        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            log_area.empty()
            st.error(f"Analysis failed: {e}")
            import traceback
            st.code(traceback.format_exc())


# ---------------------------------------------------------------------------
# PAGE 2: REVIEW DASHBOARD
# ---------------------------------------------------------------------------
elif page == "Review Dashboard":
    st.title("Review Dashboard")

    reviews = list_reviews()
    if not reviews:
        st.info("No reviews yet. Go to **Upload & Analyze** to run your first review.")
        st.stop()

    review_options = {
        f"#{r['id']} - {r['contract_name']} ({r['date'][:10]})": r["id"]
        for r in reviews
    }

    default_idx = 0
    if "current_review_id" in st.session_state:
        for i, (_, rid) in enumerate(review_options.items()):
            if rid == st.session_state["current_review_id"]:
                default_idx = i
                break

    selected_label = st.selectbox("Select Review", list(review_options.keys()), index=default_idx)
    review_id = review_options[selected_label]

    review = get_review(review_id)
    if not review:
        st.error("Review not found.")
        st.stop()

    flags = json.loads(review["flags_json"])
    summary = json.loads(review["summary_json"])
    metadata = json.loads(review["metadata_json"])
    flag_actions = {fa["flag_id"]: fa for fa in get_review_flags(review_id)}

    # Summary metrics
    st.markdown("### Summary")
    risk_bd = summary.get("risk_breakdown", {})
    cls_bd = summary.get("classification_breakdown", {})

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Clauses", summary.get("total_clauses_analyzed", len(flags)))
    c2.metric("High Risk", risk_bd.get("High", 0))
    c3.metric("Medium Risk", risk_bd.get("Medium", 0))
    c4.metric("Low Risk", risk_bd.get("Low", 0))
    c5.metric("Non-Compliant", summary.get("non_compliant_count", 0))

    pending = sum(1 for fa in flag_actions.values() if fa["reviewer_action"] == "pending")
    accepted = sum(1 for fa in flag_actions.values() if fa["reviewer_action"] == "accepted")
    rejected = sum(1 for fa in flag_actions.values() if fa["reviewer_action"] == "rejected")
    c6.metric("Pending Review", pending)

    st.markdown(
        f"**Accepted:** {accepted} | **Rejected:** {rejected} | "
        f"**Mode:** {metadata.get('analysis_mode', 'N/A')} | "
        f"**Model:** {metadata.get('embedding_model', 'N/A')}"
    )

    st.markdown("---")

    # Filters
    fcol1, fcol2, fcol3, fcol4 = st.columns(4)
    with fcol1:
        filter_risk = st.selectbox("Risk Level", ["All", "High", "Medium", "Low"])
    with fcol2:
        filter_cls = st.selectbox("Classification", [
            "All", "compliant", "deviation_minor", "deviation_major", "non_compliant"
        ])
    with fcol3:
        filter_action = st.selectbox("Review Status", ["All", "pending", "accepted", "rejected", "overridden"])
    with fcol4:
        filter_source = st.selectbox("Rule Source", ["All", "legal", "infosec"])

    # Apply filters
    filtered = flags

    if filter_risk != "All":
        filtered = [f for f in filtered if f["risk_level"] == filter_risk]
    if filter_cls != "All":
        filtered = [f for f in filtered if f["classification"] == filter_cls]
    if filter_action != "All":
        filtered = [
            f for f in filtered
            if flag_actions.get(f["flag_id"], {}).get("reviewer_action") == filter_action
        ]
    if filter_source != "All":
        filtered = [
            f for f in filtered
            if any(r.get("source") == filter_source for r in f.get("triggered_rules", []))
        ]

    # Team view filter (from sidebar)
    if team_view == "Legal":
        filtered = [
            f for f in filtered
            if any(r.get("source") == "legal" for r in f.get("triggered_rules", []))
            or not f.get("triggered_rules")
        ]
    elif team_view == "Infosec":
        filtered = [
            f for f in filtered
            if any(r.get("source") == "infosec" for r in f.get("triggered_rules", []))
        ]

    # Bulk actions
    bcol1, bcol2, bcol3 = st.columns([2, 2, 6])
    with bcol1:
        if st.button("Accept All Compliant"):
            compliant_ids = [f["flag_id"] for f in flags if f["classification"] == "compliant"]
            if compliant_ids:
                count = bulk_update_flags(review_id, compliant_ids, "accepted", reviewer_name if 'reviewer_name' in dir() else "")
                st.success(f"Accepted {count} compliant clauses.")
                st.rerun()
    with bcol2:
        if st.button("Accept All Low Risk"):
            low_ids = [f["flag_id"] for f in flags if f["risk_level"] == "Low"]
            if low_ids:
                count = bulk_update_flags(review_id, low_ids, "accepted", "")
                st.success(f"Accepted {count} low-risk clauses.")
                st.rerun()

    st.markdown(f"Showing **{len(filtered)}** of {len(flags)} clauses")

    # Display flags
    for f in filtered:
        fa = flag_actions.get(f["flag_id"], {})
        action_status = fa.get("reviewer_action", "pending") if fa else "pending"
        action_icon = {"pending": "", "accepted": "", "rejected": "", "overridden": ""}.get(action_status, "")

        risk_color = {"High": "red", "Medium": "orange", "Low": "green"}.get(f["risk_level"], "gray")
        confidence = f.get("confidence", 0)

        expander_label = (
            f"{action_icon} {f['flag_id']} | :{risk_color}[{f['risk_level']}] | "
            f"{(f.get('input_clause_section') or 'N/A')[:40]} | "
            f"{f['classification'].replace('_', ' ').title()} | "
            f"Conf: {confidence*100:.0f}%"
        )

        with st.expander(expander_label):
            # Side-by-side clause comparison
            left, right = st.columns(2)
            with left:
                st.markdown("**Incoming Clause**")
                st.text_area("", f.get("input_text", ""), height=120, disabled=True, key=f"inp_{f['flag_id']}")
            with right:
                st.markdown("**Playbook Clause**")
                pb_text = f.get("matched_playbook_text") or "No playbook match"
                st.text_area("", pb_text, height=120, disabled=True, key=f"pb_{f['flag_id']}")

            # Match info
            st.markdown(
                f"**Similarity:** {f.get('similarity_score', 0):.2f} | "
                f"**Match Type:** {f.get('match_type', 'N/A')} | "
                f"**Risk:** :{risk_color}[{f['risk_level']}] | "
                f"**Classification:** {f['classification'].replace('_', ' ').title()}"
            )

            # Explanation
            st.markdown(f"**Explanation:** {f.get('explanation', '')}")

            # Triggered rules
            triggered = f.get("triggered_rules", [])
            if triggered:
                st.markdown("**Triggered Rules:**")
                for r in triggered:
                    source_tag = r.get("source", "").upper()
                    st.markdown(f"- [{source_tag}] {r.get('clause', '')} (Risk: {r.get('risk', 'N/A')}, Score: {r.get('match_score', 0):.2f})")

            # Suggested redline
            if f.get("suggested_redline"):
                st.markdown("**Suggested Redline:**")
                st.info(f["suggested_redline"])

            # Reviewer actions
            st.markdown("---")
            st.markdown(f"**Review Status:** {action_icon} {action_status.upper()}")
            if fa and fa.get("reviewer_note"):
                st.caption(f"Note: {fa['reviewer_note']}")

            note = st.text_input("Note (optional)", key=f"note_{f['flag_id']}", placeholder="Reason...")

            acol1, acol2, acol3 = st.columns(3)
            with acol1:
                if st.button("Accept", key=f"acc_{f['flag_id']}", type="primary"):
                    update_flag_action(review_id, f["flag_id"], "accepted", note, review.get("reviewer", ""))
                    st.rerun()
            with acol2:
                if st.button("Reject", key=f"rej_{f['flag_id']}"):
                    update_flag_action(review_id, f["flag_id"], "rejected", note, review.get("reviewer", ""))
                    st.rerun()
            with acol3:
                if st.button("Override", key=f"ovr_{f['flag_id']}"):
                    update_flag_action(review_id, f["flag_id"], "overridden", note, review.get("reviewer", ""))
                    st.rerun()


# ---------------------------------------------------------------------------
# PAGE 3: HISTORY
# ---------------------------------------------------------------------------
elif page == "History":
    st.title("Review History")

    reviews = list_reviews()
    if not reviews:
        st.info("No reviews yet.")
        st.stop()

    # Aggregate stats
    stats = get_review_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Reviews", stats["total_reviews"])
    c2.metric("Avg Flags/Contract", stats["avg_flags_per_contract"])
    common = stats.get("common_deviations", {})
    top_dev = max(common, key=common.get) if common else "N/A"
    c3.metric("Most Common Deviation", top_dev.replace("_", " ").title() if top_dev != "N/A" else "N/A")

    st.markdown("---")
    st.markdown("### Past Reviews")

    for r in reviews:
        col1, col2, col3, col4 = st.columns([4, 2, 2, 2])
        col1.write(f"**#{r['id']}** - {r['contract_name']}")
        col2.write(r["date"][:10] if r.get("date") else "N/A")
        col3.write(r.get("analysis_mode", "N/A"))
        if col4.button("Open", key=f"open_{r['id']}"):
            st.session_state["current_review_id"] = r["id"]
            st.info("Switch to **Review Dashboard** in the sidebar.")

    # Rule effectiveness report
    st.markdown("---")
    st.markdown("### Rule Effectiveness Report")
    st.caption("Track which rules trigger most and how often they are rejected (false positives).")

    rule_data = get_rule_effectiveness()
    if rule_data:
        import pandas as pd
        df = pd.DataFrame(rule_data)
        df = df[["rule_id", "source", "clause", "triggered", "accepted", "rejected", "false_positive_rate"]]
        df.columns = ["Rule ID", "Source", "Clause", "Triggered", "Accepted", "Rejected", "FP Rate"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No reviewer actions recorded yet. Review some flags to see rule effectiveness data.")
