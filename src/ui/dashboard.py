"""
Fan360 Streamlit Demonstration Interface
Minimal educational interface for inspecting pipeline runs, data quality audits,
fan profiles, segment membership reasons, and consent-eligible activation audiences.
"""

import json
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
import streamlit as st

from src.pipeline.db_loader import DatabaseLoader
from src.ai.schema import ProposedSegment, SegmentFilter
from src.ai.provider import get_llm_adapter
from src.ai.evaluator import AudienceEvaluator

st.set_page_config(
    page_title="Fan360 — Motorsport Fan Data Platform",
    page_icon="🏎️",
    layout="wide",
)

db_loader = DatabaseLoader()


def load_runs():
    sql = """
        SELECT run_id, dataset_name, as_of_timestamp, started_at, completed_at, status,
               reconciliation_status, raw_records_count, accepted_records_count,
               quarantined_records_count, duplicates_removed_count, profiles_count,
               memberships_count, activation_count, audit_details
        FROM pipeline_runs
        ORDER BY started_at DESC
        LIMIT 20;
    """
    try:
        with db_loader.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql)
                return cur.fetchall()
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        return []


def load_quarantine(run_id: str):
    sql = """
        SELECT source_table, record_id, reason_code, raw_payload, created_at
        FROM quarantine_records
        WHERE run_id = %s
        ORDER BY id ASC
        LIMIT 100;
    """
    try:
        with db_loader.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (run_id,))
                return cur.fetchall()
    except Exception as e:
        st.error(f"Failed to query quarantine records: {e}")
        return []


def load_segments():
    sql = """
        SELECT d.segment_code, d.segment_name, d.description,
               COUNT(m.fan_id) FILTER (WHERE m.qualifies = 1) AS total_qualified,
               COUNT(m.fan_id) FILTER (WHERE m.qualifies = 1 AND m.activation_eligible = 1) AS activation_eligible
        FROM segment_definitions d
        LEFT JOIN fan_segment_memberships m ON d.segment_code = m.segment_code
        GROUP BY d.segment_code, d.segment_name, d.description
        ORDER BY d.segment_name;
    """
    try:
        with db_loader.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql)
                return cur.fetchall()
    except Exception as e:
        st.error(f"Failed to query segments: {e}")
        return []


def load_segment_members(segment_code: str, activation_only: bool = False, limit: int = 50):
    where_sql = "m.segment_code = %s AND m.qualifies = 1"
    if activation_only:
        where_sql += " AND m.activation_eligible = 1"

    sql = f"""
        SELECT m.fan_id, p.first_name, p.last_name, p.email, p.country,
               p.marketing_consent_status, m.activation_eligible, m.reason
        FROM fan_segment_memberships m
        JOIN fan_profiles p ON m.fan_id = p.fan_id
        WHERE {where_sql}
        ORDER BY m.fan_id
        LIMIT %s;
    """
    try:
        with db_loader.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (segment_code, limit))
                return cur.fetchall()
    except Exception as e:
        st.error(f"Failed to query segment members: {e}")
        return []


def load_fan(fan_id: str):
    sql_fan = "SELECT * FROM fan_profiles WHERE fan_id = %s;"
    sql_mem = """
        SELECT m.segment_code, d.segment_name, m.qualifies, m.activation_eligible, m.reason
        FROM fan_segment_memberships m
        JOIN segment_definitions d ON m.segment_code = d.segment_code
        WHERE m.fan_id = %s AND m.qualifies = 1;
    """
    try:
        with db_loader.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql_fan, (fan_id,))
                fan = cur.fetchone()
                if not fan:
                    return None, []
                cur.execute(sql_mem, (fan_id,))
                memberships = cur.fetchall()
                return fan, memberships
    except Exception as e:
        st.error(f"Failed to load fan: {e}")
        return None, []


# --- Streamlit UI Layout ---

st.title("🏎️ Fan360 — Motorsport Fan Data & Audience Segmentation")
st.caption("Fictional Team: Apex Velocity Racing | Educational Portfolio Platform")

runs = load_runs()

if not runs:
    st.warning("No pipeline runs found in the database. Run `python scripts/run_pipeline.py` first.")
    st.stop()

# Header Metrics
latest_run = runs[0]
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Latest Run", latest_run["run_id"][:15] + "...")
col2.metric("Raw Rows", f"{latest_run['raw_records_count']:,}")
col3.metric("Fan Profiles", f"{latest_run['profiles_count']:,}")
col4.metric("Audience Memberships", f"{latest_run['memberships_count']:,}")
col5.metric(
    "Reconciliation",
    latest_run["reconciliation_status"],
    delta="Balanced" if latest_run["reconciliation_status"] == "BALANCED" else "Discrepancy"
)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Pipeline Runs & Audit",
    "🛡️ Data Quality & Quarantine",
    "🎯 Audience Segments & Activation",
    "👤 Fan 360 Search",
    "🤖 AI Audience Builder",
])

with tab1:
    st.subheader("Pipeline Execution Runs & Reconciliation Audit")
    runs_df = pd.DataFrame(runs)
    display_cols = [
        "run_id", "dataset_name", "status", "reconciliation_status",
        "raw_records_count", "accepted_records_count", "quarantined_records_count",
        "duplicates_removed_count", "profiles_count", "activation_count", "started_at"
    ]
    st.dataframe(runs_df[display_cols], use_container_width=True)

    st.markdown("""
    **Reconciliation Formula**:
    `Raw Ingestion = Accepted Rows + Quarantined Rows + Duplicates Removed`
    """)

with tab2:
    st.subheader("Data Quality Engine & Quarantined Injected Defects")
    selected_run = st.selectbox("Select Pipeline Run", [r["run_id"] for r in runs], key="q_run")
    quarantines = load_quarantine(selected_run)

    if quarantines:
        q_df = pd.DataFrame(quarantines)
        col_q1, col_q2 = st.columns([1, 2])

        with col_q1:
            st.write("**Quarantine Reasons Breakdown**")
            reason_counts = q_df["reason_code"].value_counts()
            st.bar_chart(reason_counts)

        with col_q2:
            st.write(f"**Sample Quarantined Records (Showing up to 100)**")
            st.dataframe(q_df[["source_table", "record_id", "reason_code", "created_at"]], use_container_width=True)

        with st.expander("Inspect Raw Quarantined Payloads"):
            for idx, row in q_df.head(10).iterrows():
                st.code(f"[{row['source_table']}] ID: {row['record_id']} | Reason: {row['reason_code']}\nPayload: {row['raw_payload']}")
    else:
        st.info("No quarantined records recorded for this run.")

with tab3:
    st.subheader("Audience Segments & Consent-Governed Activation Preview")
    segments = load_segments()
    if segments:
        seg_df = pd.DataFrame(segments)
        st.dataframe(seg_df[["segment_name", "segment_code", "total_qualified", "activation_eligible", "description"]], use_container_width=True)

        st.divider()
        st.write("### Audience Member Preview")
        seg_choice = st.selectbox("Choose Segment", [s["segment_code"] for s in segments], format_func=lambda x: f"{x}")
        activation_only = st.checkbox("Only show marketing consent-eligible fans (OPT_IN)", value=True)

        members = load_segment_members(seg_choice, activation_only=activation_only, limit=50)
        if members:
            m_df = pd.DataFrame(members)
            st.dataframe(m_df[["fan_id", "first_name", "last_name", "email", "country", "marketing_consent_status", "activation_eligible", "reason"]], use_container_width=True)
        else:
            st.info("No members found matching the selected criteria.")

with tab4:
    st.subheader("Fan 360 Profile Explorer")
    fan_search_id = st.text_input("Enter Fan ID (e.g. FAN_000001, FAN_000002)", value="FAN_000001")
    if fan_search_id:
        fan, memberships = load_fan(fan_search_id.strip())
        if fan:
            f_col1, f_col2, f_col3 = st.columns(3)
            with f_col1:
                st.markdown(f"### {fan['first_name']} {fan['last_name']}")
                st.write(f"**Fan ID**: `{fan['fan_id']}`")
                st.write(f"**Email**: `{fan['email']}`")
                st.write(f"**Location**: {fan['country']} ({fan['language']})")
                st.write(f"**Preferred Driver**: 🏎️ {fan['preferred_driver']}")

            with f_col2:
                st.markdown("### Purchasing Activity")
                st.write(f"**Completed Orders**: {fan['valid_completed_order_count']}")
                st.write(f"**Total Valid Spend**: ${float(fan['total_valid_spend']):.2f} USD")
                st.write(f"**Last Activity**: {fan['last_activity_time']}")

            with f_col3:
                st.markdown("### Consent & Status")
                consent_status = fan['marketing_consent_status']
                if consent_status == "OPT_IN":
                    st.success(f"Consent Status: **{consent_status}** (Eligible for Campaigns)")
                elif consent_status == "OPT_OUT":
                    st.error(f"Consent Status: **{consent_status}** (Strictly Ineligible)")
                else:
                    st.warning(f"Consent Status: **{consent_status}** (Missing/Unconfirmed)")

            st.divider()
            st.write("### Qualified Segment Memberships & Technical Reasons")
            if memberships:
                for m in memberships:
                    with st.expander(f"✅ {m['segment_name']} (`{m['segment_code']}`)", expanded=True):
                        st.write(f"**Reason**: {m['reason']}")
                        st.write(f"**Activation Eligible**: {'Yes (Consent OPT_IN)' if m['activation_eligible'] else 'No (Consent Excluded)'}")
            else:
                st.info("Fan does not currently qualify for any configured audience segments.")
        else:
            st.error(f"Fan with ID '{fan_search_id}' not found in database.")

with tab5:
    st.subheader("AI Audience Requirement Interpreter")
    st.caption("Translate natural-language requirements into structured, reviewable, consent-governed segment previews.")

    st.info(
        "ℹ️ **Notice**: This is an educational demonstration feature modeling natural-language segment interpretation "
        "and deterministic consent enforcement. It does **not** connect to or integrate with Adobe AEP or RTCDP."
    )

    # Initialize session state for AI Audience Builder
    if "ai_proposal" not in st.session_state:
        st.session_state.ai_proposal = None
    if "ai_mode" not in st.session_state:
        st.session_state.ai_mode = None
    if "ai_preview_result" not in st.session_state:
        st.session_state.ai_preview_result = None

    adapter = get_llm_adapter()
    evaluator = AudienceEvaluator(db_loader)

    st.warning("⚠️ **Privacy Safeguard**: Do NOT input personal names, real customer email addresses, credentials, or secrets. The model only receives general audience criteria and allowlisted schema definitions.")

    # Sample query presets
    st.write("**Quick Example Prompts:**")
    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    if p_col1.button("Repeat Purchasers", use_container_width=True):
        st.session_state.preset_prompt = "Find repeat purchasers who have placed 2 or more orders"
    if p_col2.button("High Spenders (>$250)", use_container_width=True):
        st.session_state.preset_prompt = "Fans who have spent at least $250 on merchandise"
    if p_col3.button("Lucas Rossi Fans (Brazil)", use_container_width=True):
        st.session_state.preset_prompt = "Fans whose preferred driver is Lucas Rossi and country is BRA"
    if p_col4.button("Ambiguous 'Super Fans'", use_container_width=True):
        st.session_state.preset_prompt = "Target our super fans and loyal members"

    user_prompt = st.text_input(
        "Describe your audience in plain English:",
        value=st.session_state.get("preset_prompt", "Find repeat purchasers who have opted into marketing"),
        key="ai_prompt_input",
    )

    if st.button("🚀 Generate Segment Proposal", type="primary"):
        st.session_state.ai_preview_result = None
        try:
            with st.spinner("Interpreting requirement and validating schema..."):
                proposal, mode, metadata = adapter.interpret_request(user_prompt)
                st.session_state.ai_proposal = proposal
                st.session_state.ai_mode = mode
                st.session_state.ai_metadata = metadata
        except Exception as e:
            st.error(f"Interpretation failed: {e}")

    # Display Proposal & Review Interface
    if st.session_state.ai_proposal:
        proposal: ProposedSegment = st.session_state.ai_proposal
        mode_label = st.session_state.ai_mode
        ai_meta = getattr(st.session_state, "ai_metadata", {}) or {}

        st.divider()

        # Provider Status Badge
        b_col1, b_col2 = st.columns([2, 3])
        latency_ms = ai_meta.get("latency_ms")
        latency_str = f" ({latency_ms:.1f}ms)" if latency_ms is not None else ""
        with b_col1:
            if "mock" in mode_label.lower():
                st.warning(f"🏷️ **Status**: `{mode_label}`{latency_str}")
            else:
                st.success(f"🏷️ **Status**: `{mode_label}`{latency_str}")
        with b_col2:
            st.markdown(f"**Proposed Segment**: `{proposal.name}` — *{proposal.description}*")

        # Clarification prompt if required
        if proposal.clarification_required:
            st.warning(f"⚠️ **Clarification Required**: {proposal.clarification_question}")
            st.caption(f"Reason: {proposal.explanation}")
        else:
            st.markdown(f"**Mapping Explanation**: {proposal.explanation}")

            # Editable Review Section
            st.write("#### 🛠️ Proposed Attribute Filters (Conjunctive AND):")
            edited_filters = []
            if proposal.filters:
                for idx, flt in enumerate(proposal.filters):
                    fc1, fc2, fc3 = st.columns([2, 1, 2])
                    fc1.code(flt.field)
                    fc2.code(flt.operator)

                    # Dynamic input based on type
                    if isinstance(flt.value, (int, float)):
                        new_val = fc3.number_input(
                            f"Filter value ({flt.field})",
                            value=flt.value,
                            key=f"val_{idx}",
                            label_visibility="collapsed",
                        )
                        edited_filters.append(SegmentFilter(field=flt.field, operator=flt.operator, value=new_val))
                    else:
                        new_val = fc3.text_input(
                            f"Filter value ({flt.field})",
                            value=str(flt.value),
                            key=f"val_{idx}",
                            label_visibility="collapsed",
                        )
                        edited_filters.append(SegmentFilter(field=flt.field, operator=flt.operator, value=new_val))
            else:
                st.info("No behavioral filters were specified.")

            # Explicit Preview Action
            st.markdown("---")
            p_btn_col1, p_btn_col2 = st.columns([1, 3])
            with p_btn_col1:
                preview_clicked = st.button("🔍 Preview Audience (Explicit Action)", type="secondary")

            if preview_clicked:
                try:
                    with st.spinner("Executing parameterized preview and enforcing mandatory consent..."):
                        # Construct edited proposal
                        updated_proposal = ProposedSegment(
                            name=proposal.name,
                            description=proposal.description,
                            filters=edited_filters,
                            explanation=proposal.explanation,
                            clarification_required=False,
                            clarification_question=None,
                        )
                        st.session_state.ai_proposal = updated_proposal
                        preview_res = evaluator.evaluate_preview(updated_proposal, preview_limit=10)
                        st.session_state.ai_preview_result = preview_res
                except Exception as e:
                    st.error(f"Preview evaluation failed: {e}")

    # Display Bounded Preview Results
    if st.session_state.ai_preview_result:
        p_res = st.session_state.ai_preview_result
        st.write("### 👥 Audience Preview & Consent Governance")

        m_col1, m_col2, m_col3 = st.columns(3)
        total_m = p_res["total_matched"]
        eligible_m = p_res["consent_eligible"]
        excluded_m = max(0, total_m - eligible_m)
        exclusion_rate = round((excluded_m / total_m * 100), 1) if total_m > 0 else 0.0

        m_col1.metric("1. Total Behavioral Matched", f"{total_m:,}", help="Profiles matching behavioral filter conditions.")
        m_col2.metric("2. Consent-Eligible for Activation", f"{eligible_m:,}", delta="OPT_IN Only", help="Profiles strictly verified for marketing consent.")
        m_col3.metric("3. Excluded by Consent Policy", f"{excluded_m:,}", delta=f"{exclusion_rate}% Protected", delta_color="inverse")

        st.caption("🔒 **Mandatory Governance**: Non-consenting fans (OPT_OUT/NONE) are strictly excluded from activation eligibility.")

        profiles = p_res.get("preview_profiles", [])
        if profiles:
            p_df = pd.DataFrame(profiles)
            st.dataframe(
                p_df[["fan_id", "name", "email", "country", "preferred_driver", "orders_count", "total_spend", "marketing_consent", "activation_eligible"]],
                use_container_width=True,
            )
        else:
            st.info("No profiles match the requested filter criteria.")

