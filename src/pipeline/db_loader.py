"""
Fan360 Database Loader & Idempotent Persistence
Handles schema creation and idempotent loading of fan profiles, segment memberships,
quarantine records, and pipeline execution audits into PostgreSQL.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

import psycopg2
from psycopg2.extras import execute_values
import yaml
from pyspark.sql import DataFrame

from src.pipeline.schema import QuarantineRecord, RunAudit


DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        run_id VARCHAR(64) PRIMARY KEY,
        dataset_name VARCHAR(64) NOT NULL,
        as_of_timestamp TIMESTAMPTZ NOT NULL,
        started_at TIMESTAMPTZ NOT NULL,
        completed_at TIMESTAMPTZ NOT NULL,
        status VARCHAR(32) NOT NULL,
        raw_records_count INT NOT NULL,
        accepted_records_count INT NOT NULL,
        quarantined_records_count INT NOT NULL,
        duplicates_removed_count INT NOT NULL,
        profiles_count INT NOT NULL,
        memberships_count INT NOT NULL,
        activation_count INT NOT NULL,
        reconciliation_status VARCHAR(32) NOT NULL,
        audit_details JSONB
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS quarantine_records (
        id SERIAL PRIMARY KEY,
        run_id VARCHAR(64) NOT NULL,
        source_table VARCHAR(64) NOT NULL,
        record_id VARCHAR(64) NOT NULL,
        reason_code VARCHAR(64) NOT NULL,
        raw_payload JSONB,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_quarantine_run ON quarantine_records(run_id);
    CREATE INDEX IF NOT EXISTS idx_quarantine_reason ON quarantine_records(reason_code);
    """,
    """
    CREATE TABLE IF NOT EXISTS segment_definitions (
        segment_code VARCHAR(64) PRIMARY KEY,
        segment_name VARCHAR(128) NOT NULL,
        description TEXT,
        rules_json JSONB
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fan_profiles (
        fan_id VARCHAR(64) PRIMARY KEY,
        first_name VARCHAR(128),
        last_name VARCHAR(128),
        email VARCHAR(256),
        country VARCHAR(32),
        language VARCHAR(16),
        preferred_driver VARCHAR(128),
        created_at TIMESTAMPTZ,
        last_activity_time TIMESTAMPTZ,
        valid_completed_order_count INT DEFAULT 0,
        total_valid_spend NUMERIC(12, 2) DEFAULT 0.00,
        marketing_consent_status VARCHAR(32) DEFAULT 'NONE',
        last_run_id VARCHAR(64),
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_fan_consent ON fan_profiles(marketing_consent_status);
    CREATE INDEX IF NOT EXISTS idx_fan_spend ON fan_profiles(total_valid_spend);
    """,
    """
    CREATE TABLE IF NOT EXISTS fan_segment_memberships (
        fan_id VARCHAR(64) NOT NULL,
        segment_code VARCHAR(64) NOT NULL,
        qualifies INT NOT NULL DEFAULT 1,
        activation_eligible INT NOT NULL DEFAULT 0,
        reason TEXT,
        last_run_id VARCHAR(64),
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (fan_id, segment_code)
    );
    CREATE INDEX IF NOT EXISTS idx_membership_segment ON fan_segment_memberships(segment_code);
    """,
    """
    CREATE TABLE IF NOT EXISTS activation_audiences (
        fan_id VARCHAR(64) NOT NULL,
        segment_code VARCHAR(64) NOT NULL,
        email VARCHAR(256),
        first_name VARCHAR(128),
        last_name VARCHAR(128),
        consent_status VARCHAR(32),
        last_run_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (fan_id, segment_code, last_run_id)
    );
    CREATE INDEX IF NOT EXISTS idx_activation_run_segment ON activation_audiences(last_run_id, segment_code);
    """
]


class DatabaseLoader:
    """Manages PostgreSQL schema creation and idempotent batch writes."""

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = self._load_config(config_path)
        db_cfg = self.config.get("database", {})
        self.host = os.environ.get("FAN360_DB_HOST", db_cfg.get("host", "localhost"))
        self.port = int(os.environ.get("FAN360_DB_PORT", db_cfg.get("port", 5432)))
        self.dbname = os.environ.get("FAN360_DB_NAME", db_cfg.get("dbname", "fan360"))
        self.user = os.environ.get("FAN360_DB_USER", db_cfg.get("user", "tejashr"))
        self.password = os.environ.get("FAN360_DB_PASSWORD", db_cfg.get("password", ""))

    def _load_config(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @contextmanager
    def get_connection(self) -> Iterator[psycopg2.extensions.connection]:
        conn = psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            connect_timeout=5,
        )
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        """Creates tables, constraints, and indexes idempotently."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                for ddl in DDL_STATEMENTS:
                    cur.execute(ddl)

    def sync_segment_definitions(self, rules_path: str = "config/segment_rules.yaml") -> None:
        """Populates or updates the segment_definitions lookup table."""
        if not os.path.exists(rules_path):
            return
        with open(rules_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        segments = data.get("segments", {})
        rows = []
        for code, meta in segments.items():
            rows.append((
                code,
                meta.get("name", code),
                meta.get("description", ""),
                json.dumps(meta.get("rules", {})),
            ))

        sql = """
        INSERT INTO segment_definitions (segment_code, segment_name, description, rules_json)
        VALUES %s
        ON CONFLICT (segment_code) DO UPDATE SET
            segment_name = EXCLUDED.segment_name,
            description = EXCLUDED.description,
            rules_json = EXCLUDED.rules_json;
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, sql, rows)

    def load_profiles(self, profiles_df: DataFrame, run_id: str) -> int:
        """Idempotently upserts fan profiles into fan_profiles table."""
        rows = profiles_df.collect()
        if not rows:
            return 0

        data = []
        now_ts = datetime.now(timezone.utc)
        for r in rows:
            d = r.asDict()
            data.append((
                d["fan_id"],
                d.get("first_name"),
                d.get("last_name"),
                d.get("email"),
                d.get("country"),
                d.get("language"),
                d.get("preferred_driver"),
                d.get("created_at"),
                d.get("last_activity_time"),
                int(d.get("valid_completed_order_count", 0)),
                float(d.get("total_valid_spend", 0.0)),
                d.get("marketing_consent_status", "NONE"),
                run_id,
                now_ts,
            ))

        sql = """
        INSERT INTO fan_profiles (
            fan_id, first_name, last_name, email, country, language, preferred_driver,
            created_at, last_activity_time, valid_completed_order_count, total_valid_spend,
            marketing_consent_status, last_run_id, updated_at
        ) VALUES %s
        ON CONFLICT (fan_id) DO UPDATE SET
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            email = EXCLUDED.email,
            country = EXCLUDED.country,
            language = EXCLUDED.language,
            preferred_driver = EXCLUDED.preferred_driver,
            last_activity_time = EXCLUDED.last_activity_time,
            valid_completed_order_count = EXCLUDED.valid_completed_order_count,
            total_valid_spend = EXCLUDED.total_valid_spend,
            marketing_consent_status = EXCLUDED.marketing_consent_status,
            last_run_id = EXCLUDED.last_run_id,
            updated_at = EXCLUDED.updated_at;
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, sql, data, page_size=1000)
        return len(data)

    def load_memberships(self, memberships_df: DataFrame, run_id: str) -> int:
        """Idempotently upserts fan segment memberships."""
        rows = memberships_df.collect()
        if not rows:
            return 0

        data = []
        now_ts = datetime.now(timezone.utc)
        for r in rows:
            d = r.asDict()
            data.append((
                d["fan_id"],
                d["segment_code"],
                int(d.get("qualifies", 1)),
                int(d.get("activation_eligible", 0)),
                d.get("reason", ""),
                run_id,
                now_ts,
            ))

        sql = """
        INSERT INTO fan_segment_memberships (
            fan_id, segment_code, qualifies, activation_eligible, reason, last_run_id, updated_at
        ) VALUES %s
        ON CONFLICT (fan_id, segment_code) DO UPDATE SET
            qualifies = EXCLUDED.qualifies,
            activation_eligible = EXCLUDED.activation_eligible,
            reason = EXCLUDED.reason,
            last_run_id = EXCLUDED.last_run_id,
            updated_at = EXCLUDED.updated_at;
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, sql, data, page_size=1000)
        return len(data)

    def load_activation_audiences(self, activation_df: DataFrame, run_id: str) -> int:
        """Stores consent-filtered activation audiences for the run."""
        rows = activation_df.collect()
        if not rows:
            return 0

        data = []
        now_ts = datetime.now(timezone.utc)
        for r in rows:
            d = r.asDict()
            data.append((
                d["fan_id"],
                d["segment_code"],
                d.get("email"),
                d.get("first_name"),
                d.get("last_name"),
                d.get("consent_status", "OPT_IN"),
                run_id,
                now_ts,
            ))

        sql = """
        INSERT INTO activation_audiences (
            fan_id, segment_code, email, first_name, last_name, consent_status, last_run_id, created_at
        ) VALUES %s
        ON CONFLICT (fan_id, segment_code, last_run_id) DO UPDATE SET
            email = EXCLUDED.email,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            consent_status = EXCLUDED.consent_status;
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, sql, data, page_size=1000)
        return len(data)

    def load_quarantine_records(self, quarantines: List[QuarantineRecord], run_id: str) -> int:
        """Stores quarantined records with reasons."""
        if not quarantines:
            return 0

        data = []
        now_ts = datetime.now(timezone.utc)
        for q in quarantines:
            data.append((
                run_id,
                q.source_table,
                q.record_id,
                q.reason_code,
                json.dumps(q.raw_payload),
                now_ts,
            ))

        sql = """
        INSERT INTO quarantine_records (
            run_id, source_table, record_id, reason_code, raw_payload, created_at
        ) VALUES %s;
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Remove existing quarantine records for this run if re-running
                cur.execute("DELETE FROM quarantine_records WHERE run_id = %s;", (run_id,))
                execute_values(cur, sql, data, page_size=1000)
        return len(data)

    def record_run_audit(self, audit: RunAudit) -> None:
        """Saves run-level audit and reconciliation metrics."""
        sql = """
        INSERT INTO pipeline_runs (
            run_id, dataset_name, as_of_timestamp, started_at, completed_at, status,
            raw_records_count, accepted_records_count, quarantined_records_count,
            duplicates_removed_count, profiles_count, memberships_count, activation_count,
            reconciliation_status, audit_details
        ) VALUES (
            %(run_id)s, %(dataset_name)s, %(as_of)s, %(started_at)s, %(completed_at)s, %(status)s,
            %(raw_cnt)s, %(acc_cnt)s, %(quar_cnt)s, %(dup_cnt)s, %(prof_cnt)s, %(mem_cnt)s, %(act_cnt)s,
            %(rec_status)s, %(details)s
        )
        ON CONFLICT (run_id) DO UPDATE SET
            status = EXCLUDED.status,
            completed_at = EXCLUDED.completed_at,
            raw_records_count = EXCLUDED.raw_records_count,
            accepted_records_count = EXCLUDED.accepted_records_count,
            quarantined_records_count = EXCLUDED.quarantined_records_count,
            duplicates_removed_count = EXCLUDED.duplicates_removed_count,
            profiles_count = EXCLUDED.profiles_count,
            memberships_count = EXCLUDED.memberships_count,
            activation_count = EXCLUDED.activation_count,
            reconciliation_status = EXCLUDED.reconciliation_status,
            audit_details = EXCLUDED.audit_details;
        """
        params = {
            "run_id": audit.run_id,
            "dataset_name": audit.dataset_name,
            "as_of": audit.as_of_timestamp,
            "started_at": audit.started_at,
            "completed_at": audit.completed_at,
            "status": audit.status,
            "raw_cnt": sum(audit.raw_counts.values()),
            "acc_cnt": sum(audit.accepted_counts.values()),
            "quar_cnt": sum(audit.quarantined_counts.values()),
            "dup_cnt": sum(audit.deduplicated_counts.values()),
            "prof_cnt": audit.profiles_count,
            "mem_cnt": audit.memberships_count,
            "act_cnt": audit.activation_count,
            "rec_status": "BALANCED" if audit.reconciliation_balanced else "DISCREPANCY",
            "details": json.dumps(audit.details),
        }
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
