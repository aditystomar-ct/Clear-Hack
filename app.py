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
from contract_review.config import ANTHROPIC_API_KEY, PLAYBOOK_PATH, LLM_MODEL

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

st.sidebar.caption("Review Dashboard has Legal / Infosec / General tabs.")


# ---------------------------------------------------------------------------
# PAGE 1: UPLOAD & ANALYZE
# ---------------------------------------------------------------------------
if page == "Upload & Analyze":
    st.title("Upload & Analyze DPA")
    st.markdown("Compare an incoming DPA against ClearTax's standard DPA and internal rulebook using Claude.")

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
        reviewer_name = st.text_input("Reviewer Name", placeholder="Your name (optional)")

        playbook_option = st.selectbox("Playbook", ["ClearTax DPA (default)", "Custom Google Doc"])
        custom_playbook = None
        if playbook_option != "ClearTax DPA (default)":
            custom_playbook = st.text_input("Custom playbook Google Doc URL or ID")

        st.caption(f"Analysis: Direct LLM comparison using Claude ({LLM_MODEL if ANTHROPIC_API_KEY else 'NOT CONFIGURED'})")

    if not ANTHROPIC_API_KEY:
        st.warning("ANTHROPIC_API_KEY not set in .env. Analysis will not work.")

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
                reviewer=reviewer_name,
                progress_callback=progress_callback,
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
            c5.metric("Time", f"{result['metadata'].get('elapsed_seconds', '?')}s")

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
        f"**Mode:** Direct LLM | "
        f"**Model:** {metadata.get('llm_model', 'N/A')}"
    )

    st.markdown("---")

    # Check if input was a Google Doc
    doc_id = metadata.get("input_source", "")
    is_google_doc = doc_id and not doc_id.endswith(".docx") and len(doc_id) > 15

    # Load team emails once
    from contract_review.extractors import load_team_emails
    from contract_review.config import RULEBOOK_PATH
    team_emails = load_team_emails(RULEBOOK_PATH)

    # Filters
    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        filter_risk = st.selectbox("Risk Level", ["All", "High", "Medium", "Low"])
    with fcol2:
        filter_cls = st.selectbox("Classification", [
            "All", "compliant", "deviation_minor", "deviation_major", "non_compliant"
        ])
    with fcol3:
        filter_action = st.selectbox("Review Status", ["All", "pending", "accepted", "rejected"])

    def apply_filters(flag_list):
        result = flag_list
        if filter_risk != "All":
            result = [f for f in result if f["risk_level"] == filter_risk]
        if filter_cls != "All":
            result = [f for f in result if f["classification"] == filter_cls]
        if filter_action != "All":
            result = [
                f for f in result
                if flag_actions.get(f["flag_id"], {}).get("reviewer_action") == filter_action
            ]
        return result

    # Split flags into Legal, Infosec, and General (no triggered rules)
    legal_flags = [f for f in flags if any(r.get("source") == "legal" for r in f.get("triggered_rules", []))]
    infosec_flags = [f for f in flags if any(r.get("source") == "infosec" for r in f.get("triggered_rules", []))]
    general_flags = [f for f in flags if not f.get("triggered_rules")]

    # Apply filters
    legal_filtered = apply_filters(legal_flags)
    infosec_filtered = apply_filters(infosec_flags)
    general_filtered = apply_filters(general_flags)

    # Helper to render a single flag card
    def render_flag(f, tab_key):
        fa = flag_actions.get(f["flag_id"], {})
        action_status = fa.get("reviewer_action", "pending") if fa else "pending"
        action_icon = {"pending": "", "accepted": "", "rejected": ""}.get(action_status, "")

        risk_color = {"High": "red", "Medium": "orange", "Low": "green"}.get(f["risk_level"], "gray")
        confidence = f.get("confidence", 0)

        # Show which teams are tagged
        tagged_teams = set(r.get("source", "") for r in f.get("triggered_rules", []))
        team_tags = " | ".join(t.upper() for t in sorted(tagged_teams)) if tagged_teams else "General"

        expander_label = (
            f"{action_icon} {f['flag_id']} | :{risk_color}[{f['risk_level']}] | "
            f"{team_tags} | "
            f"{(f.get('input_clause_section') or 'N/A')[:40]} | "
            f"{f['classification'].replace('_', ' ').title()} | "
            f"Conf: {confidence*100:.0f}%"
        )

        with st.expander(expander_label):
            # Side-by-side clause comparison
            left, right = st.columns(2)
            with left:
                st.markdown("**Incoming Clause**")
                st.text_area("Incoming", f.get("input_text", ""), height=120, disabled=True, key=f"inp_{tab_key}_{f['flag_id']}", label_visibility="collapsed")
            with right:
                st.markdown("**Playbook Clause**")
                pb_text = f.get("matched_playbook_text") or "No playbook match"
                st.text_area("Playbook", pb_text, height=120, disabled=True, key=f"pb_{tab_key}_{f['flag_id']}", label_visibility="collapsed")

            # Match info
            st.markdown(
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
                    team_email = team_emails.get(r.get("source", ""), "")
                    email_display = f" — {team_email}" if team_email else ""
                    st.markdown(f"- [{source_tag}]{email_display} {r.get('clause', '')} (Risk: {r.get('risk', 'N/A')})")

            # Show team emails that will receive notification
            notify_teams = tagged_teams if tagged_teams else set(team_emails.keys())
            email_list = [f"{t.upper()}: {team_emails[t]}" for t in sorted(notify_teams) if t in team_emails]
            if email_list:
                st.markdown(f"**Email notification to:** {', '.join(email_list)}")

            # Suggested redline
            if f.get("suggested_redline"):
                st.markdown("**Suggested Redline:**")
                st.info(f["suggested_redline"])

            # Reviewer actions
            st.markdown("---")
            st.markdown(f"**Review Status:** {action_icon} {action_status.upper()}")

            acol1, acol2 = st.columns(2)
            with acol1:
                if st.button("Accept", key=f"acc_{tab_key}_{f['flag_id']}", type="primary"):
                    update_flag_action(review_id, f["flag_id"], "accepted", "", review.get("reviewer", ""))

                    # Comment + highlight on Google Doc
                    if is_google_doc:
                        try:
                            from contract_review.google_doc import add_comment_single, highlight_single
                            add_comment_single(doc_id, f, team_emails)
                            highlight_single(doc_id, f)
                        except Exception as e:
                            st.error(f"Google Doc update failed: {e}")

                    # Send email to relevant team(s)
                    try:
                        from contract_review.notifications import send_flag_email
                        doc_url = f"https://docs.google.com/document/d/{doc_id}" if is_google_doc else ""
                        send_flag_email(
                            contract_name=metadata.get("contract_name", metadata.get("input_source", "")),
                            flag=f,
                            team_emails=team_emails,
                            doc_url=doc_url,
                        )
                    except Exception as e:
                        st.error(f"Email failed: {e}")

                    st.experimental_rerun()
            with acol2:
                if st.button("Reject", key=f"rej_{tab_key}_{f['flag_id']}"):
                    update_flag_action(review_id, f["flag_id"], "rejected", "", review.get("reviewer", ""))
                    st.experimental_rerun()

    # --- Tabs: Legal | Infosec | General ---
    tab_legal, tab_infosec, tab_general = st.tabs([
        f"Legal ({len(legal_filtered)})",
        f"Infosec ({len(infosec_filtered)})",
        f"General ({len(general_filtered)})",
    ])

    with tab_legal:
        st.markdown(f"**Legal team flags** — email: `{team_emails.get('legal', 'not configured')}`")
        if not legal_filtered:
            st.info("No legal flags match current filters.")
        for f in legal_filtered:
            render_flag(f, "legal")

    with tab_infosec:
        st.markdown(f"**Infosec team flags** — email: `{team_emails.get('infosec', 'not configured')}`")
        if not infosec_filtered:
            st.info("No infosec flags match current filters.")
        for f in infosec_filtered:
            render_flag(f, "infosec")

    with tab_general:
        st.markdown("**Flags with no specific rulebook match** — email sent to all teams on accept")
        if not general_filtered:
            st.info("No general flags match current filters.")
        for f in general_filtered:
            render_flag(f, "general")


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
