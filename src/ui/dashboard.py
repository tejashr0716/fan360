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

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Pipeline Runs & Audit",
    "🛡️ Data Quality & Quarantine",
    "🎯 Audience Segments & Activation",
    "👤 Fan 360 Search"
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
