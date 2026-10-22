"""
Fan360 PySpark Transformation and Audience Segmentation Pipeline
Implements consolidated fan profiles, consent resolution, window-based abandoned-cart logic,
and audience segment evaluation with explicit reason generation.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import yaml
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)
from pyspark.sql.window import Window


def get_spark_session(app_name: str = "Fan360-Pipeline", master: str = "local[2]") -> SparkSession:
    """Creates or retrieves a local Spark session with optimized settings."""
    builder = (
        SparkSession.builder.appName(app_name)
        .master(master)
        .config("spark.driver.memory", "2g")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.analyzer.failAmbiguousSelfJoin", "false")
    )
    return builder.getOrCreate()


class SparkFanPipeline:
    """PySpark ETL engine for Fan360."""

    def __init__(
        self,
        spark: Optional[SparkSession] = None,
        config_path: str = "config/config.yaml",
        rules_path: str = "config/segment_rules.yaml",
        as_of_timestamp: Optional[str] = None,
    ):
        self.spark = spark or get_spark_session()
        self.config = self._load_yaml(config_path)
        self.rules = self._load_yaml(rules_path)

        as_of_str = as_of_timestamp or self.config.get("pipeline", {}).get(
            "as_of_timestamp", "2026-10-01T00:00:00Z"
        )
        self.as_of_dt = datetime.fromisoformat(as_of_str.replace("Z", "+00:00"))
        self.as_of_str = self.as_of_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _load_yaml(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _dicts_to_df(
        self,
        records: List[Dict[str, Any]],
        schema: Optional[StructType] = None,
    ) -> DataFrame:
        if not records:
            if schema:
                return self.spark.createDataFrame([], schema)
            return self.spark.createDataFrame([], StructType([]))
        if schema:
            return self.spark.createDataFrame(records, schema)
        return self.spark.createDataFrame(records)

    def process(
        self,
        accepted_data: Dict[str, List[Dict[str, Any]]],
    ) -> Tuple[DataFrame, DataFrame, DataFrame]:
        """
        Executes full transformation on accepted records.
        Returns:
            - profiles_df: Consolidated Fan Profiles
            - memberships_df: Descriptive Segment Memberships with reasons
            - activation_df: Consent-filtered Activation Audience
        """
        fans_df = self._dicts_to_df(accepted_data.get("fans", []))
        orders_df = self._dicts_to_df(accepted_data.get("orders", []))
        web_df = self._dicts_to_df(accepted_data.get("web_events", []))
        email_df = self._dicts_to_df(accepted_data.get("email_events", []))
        consent_df = self._dicts_to_df(accepted_data.get("consent", []))

        # Handle empty fans edge case
        if fans_df.count() == 0:
            empty_prof = self.spark.createDataFrame([], StructType([
                StructField("fan_id", StringType(), False),
                StructField("first_name", StringType(), True),
                StructField("last_name", StringType(), True),
                StructField("email", StringType(), True),
                StructField("country", StringType(), True),
                StructField("language", StringType(), True),
                StructField("preferred_driver", StringType(), True),
                StructField("created_at", StringType(), True),
                StructField("last_activity_time", StringType(), True),
                StructField("valid_completed_order_count", IntegerType(), True),
                StructField("total_valid_spend", DoubleType(), True),
                StructField("marketing_consent_status", StringType(), True),
            ]))
            empty_mem = self.spark.createDataFrame([], StructType([
                StructField("fan_id", StringType(), False),
                StructField("segment_code", StringType(), False),
                StructField("qualifies", IntegerType(), False),
                StructField("activation_eligible", IntegerType(), False),
                StructField("reason", StringType(), True),
            ]))
            empty_act = self.spark.createDataFrame([], StructType([
                StructField("fan_id", StringType(), False),
                StructField("segment_code", StringType(), False),
                StructField("email", StringType(), True),
                StructField("first_name", StringType(), True),
                StructField("last_name", StringType(), True),
                StructField("consent_status", StringType(), True),
            ]))
            return empty_prof, empty_mem, empty_act

        # 1. Resolve Marketing Consent (Latest Effective Update Rule with Deterministic Tie-Breaker)
        resolved_consent_df = self._resolve_consent(consent_df)

        # 2. Orders Spend & Counts Aggregation (COMPLETED orders with amount > 0)
        orders_agg_df = self._aggregate_orders(orders_df)

        # 3. Last Activity Aggregation Across All Streams
        last_activity_df = self._compute_last_activity(fans_df, orders_df, web_df, email_df)

        # 4. Build Consolidated Fan Profiles
        profiles_df = (
            fans_df.join(orders_agg_df, on="fan_id", how="left")
            .join(last_activity_df, on="fan_id", how="left")
            .join(resolved_consent_df, on="fan_id", how="left")
            .select(
                "fan_id",
                "first_name",
                "last_name",
                "email",
                "country",
                "language",
                "preferred_driver",
                "created_at",
                F.coalesce(F.col("last_activity_time"), F.col("created_at")).alias("last_activity_time"),
                F.coalesce(F.col("valid_completed_order_count"), F.lit(0)).cast("int").alias("valid_completed_order_count"),
                F.coalesce(F.col("total_valid_spend"), F.lit(0.0)).cast("double").alias("total_valid_spend"),
                F.coalesce(F.col("marketing_consent_status"), F.lit("NONE")).alias("marketing_consent_status"),
            )
        )

        # 5. Calculate Segment Memberships & Reasons
        memberships_df = self._calculate_segment_memberships(profiles_df, web_df, email_df, orders_df, resolved_consent_df)

        # 6. Consent-Filtered Activation Audiences (Only OPT_IN fans are eligible for marketing activation)
        eligible_memberships = memberships_df.filter(F.col("activation_eligible") == 1)
        activation_df = (
            eligible_memberships.join(fans_df, on="fan_id", how="inner")
            .select(
                "fan_id",
                "segment_code",
                "email",
                "first_name",
                "last_name",
                F.lit("OPT_IN").alias("consent_status"),
            )
        )

        return profiles_df, memberships_df, activation_df

    def _resolve_consent(self, consent_df: DataFrame) -> DataFrame:
        """
        Determines the current marketing consent for each fan using the latest-effective-update rule.
        Tie-breaker: update_timestamp DESC, consent_id DESC.
        Missing or ambiguous consent defaults to NONE.
        """
        if consent_df.count() == 0:
            return self.spark.createDataFrame([], StructType([
                StructField("fan_id", StringType(), False),
                StructField("marketing_consent_status", StringType(), True),
            ]))

        # Filter valid statuses and effective updates up to as_of
        valid_consent = consent_df.filter(
            (F.col("status").isin("OPT_IN", "OPT_OUT")) &
            (F.col("update_timestamp") <= F.lit(self.as_of_str))
        )

        # Window order: latest timestamp first, break ties with consent_id
        win = Window.partitionBy("fan_id").orderBy(
            F.col("update_timestamp").desc(),
            F.col("consent_id").desc()
        )

        latest_consent = (
            valid_consent.withColumn("row_num", F.row_number().over(win))
            .filter(F.col("row_num") == 1)
            .select(
                F.col("fan_id"),
                F.col("status").alias("marketing_consent_status"),
            )
        )
        return latest_consent

    def _aggregate_orders(self, orders_df: DataFrame) -> DataFrame:
        """Aggregates valid completed orders and spend per fan."""
        if orders_df.count() == 0:
            return self.spark.createDataFrame([], StructType([
                StructField("fan_id", StringType(), False),
                StructField("valid_completed_order_count", IntegerType(), True),
                StructField("total_valid_spend", DoubleType(), True),
                StructField("last_order_time", StringType(), True),
            ]))

        valid_orders = (
            orders_df.filter(
                (F.col("order_status") == "COMPLETED") &
                (F.col("order_amount").cast("double") > 0.0) &
                (F.col("order_timestamp") <= F.lit(self.as_of_str))
            )
            .withColumn("amount_dbl", F.col("order_amount").cast("double"))
        )

        agg_df = valid_orders.groupBy("fan_id").agg(
            F.count("order_id").cast("int").alias("valid_completed_order_count"),
            F.round(F.sum("amount_dbl"), 2).cast("double").alias("total_valid_spend"),
            F.max("order_timestamp").alias("last_order_time"),
        )
        return agg_df

    def _compute_last_activity(
        self,
        fans_df: DataFrame,
        orders_df: DataFrame,
        web_df: DataFrame,
        email_df: DataFrame,
    ) -> DataFrame:
        """Finds the maximum timestamp across web events, email events, orders, and profile creation."""
        timestamps: List[DataFrame] = []

        if web_df.count() > 0:
            timestamps.append(
                web_df.filter(F.col("event_timestamp") <= F.lit(self.as_of_str))
                .select("fan_id", F.col("event_timestamp").alias("act_time"))
            )
        if email_df.count() > 0:
            timestamps.append(
                email_df.filter(F.col("event_timestamp") <= F.lit(self.as_of_str))
                .select("fan_id", F.col("event_timestamp").alias("act_time"))
            )
        if orders_df.count() > 0:
            timestamps.append(
                orders_df.filter(F.col("order_timestamp") <= F.lit(self.as_of_str))
                .select("fan_id", F.col("order_timestamp").alias("act_time"))
            )
        timestamps.append(
            fans_df.select("fan_id", F.col("created_at").alias("act_time"))
        )

        combined = timestamps[0]
        for df in timestamps[1:]:
            combined = combined.union(df)

        last_act = combined.groupBy("fan_id").agg(
            F.max("act_time").alias("last_activity_time")
        )
        return last_act

    def _calculate_segment_memberships(
        self,
        profiles_df: DataFrame,
        web_df: DataFrame,
        email_df: DataFrame,
        orders_df: DataFrame,
        resolved_consent_df: DataFrame,
    ) -> DataFrame:
        """Evaluates all 5 configured segment rules and returns qualifications with explanatory reason fields."""
        as_of_ts = F.to_timestamp(F.lit(self.as_of_str))
        rules_cfg = self.rules.get("segments", {})

        # Date math helpers
        prof_with_days = profiles_df.withColumn(
            "act_ts", F.to_timestamp(F.col("last_activity_time"))
        ).withColumn(
            "days_since_activity",
            F.floor((F.unix_timestamp(as_of_ts) - F.unix_timestamp(F.col("act_ts"))) / 86400).cast("int")
        )

        membership_rows: List[DataFrame] = []

        # 1. Repeat Buyers (valid completed orders >= 2)
        rep_cfg = rules_cfg.get("repeat_buyers", {}).get("rules", {})
        min_orders = rep_cfg.get("min_completed_orders", 2)
        repeat_buyers = prof_with_days.filter(
            F.col("valid_completed_order_count") >= min_orders
        ).select(
            F.col("fan_id"),
            F.lit("repeat_buyers").alias("segment_code"),
            F.lit(1).alias("qualifies"),
            (F.col("marketing_consent_status") == "OPT_IN").cast("int").alias("activation_eligible"),
            F.concat(
                F.lit("Placed "),
                F.col("valid_completed_order_count"),
                F.lit(f" completed orders (threshold: >= {min_orders}).")
            ).alias("reason"),
        )
        membership_rows.append(repeat_buyers)

        # 2. High-Spending Buyers (total valid spend >= $250.00)
        hsp_cfg = rules_cfg.get("high_spending_buyers", {}).get("rules", {})
        min_spend = float(hsp_cfg.get("min_total_spend", 250.00))
        high_spending = prof_with_days.filter(
            F.col("total_valid_spend") >= min_spend
        ).select(
            F.col("fan_id"),
            F.lit("high_spending_buyers").alias("segment_code"),
            F.lit(1).alias("qualifies"),
            (F.col("marketing_consent_status") == "OPT_IN").cast("int").alias("activation_eligible"),
            F.concat(
                F.lit("Accumulated $"),
                F.format_number(F.col("total_valid_spend"), 2),
                F.lit(f" USD in valid completed spend (threshold: >= ${min_spend:.2f}).")
            ).alias("reason"),
        )
        membership_rows.append(high_spending)

        # 3. Engaged Non-Buyers (Activity within past 90d AND 0 completed orders)
        eng_cfg = rules_cfg.get("engaged_non_buyers", {}).get("rules", {})
        window_days = eng_cfg.get("window_days", 90)

        # Count events in the last 90 days per fan
        cutoff_90d = (self.as_of_dt - timedelta(days=window_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent_events = []
        if web_df.count() > 0:
            recent_events.append(
                web_df.filter(
                    (F.col("event_timestamp") >= F.lit(cutoff_90d)) &
                    (F.col("event_timestamp") <= F.lit(self.as_of_str))
                ).select("fan_id")
            )
        if email_df.count() > 0:
            recent_events.append(
                email_df.filter(
                    (F.col("event_timestamp") >= F.lit(cutoff_90d)) &
                    (F.col("event_timestamp") <= F.lit(self.as_of_str))
                ).select("fan_id")
            )

        if recent_events:
            all_recent = recent_events[0]
            for ev_df in recent_events[1:]:
                all_recent = all_recent.union(ev_df)
            recent_counts = all_recent.groupBy("fan_id").agg(F.count(F.lit(1)).alias("event_count"))
        else:
            recent_counts = self.spark.createDataFrame([], StructType([
                StructField("fan_id", StringType(), False),
                StructField("event_count", IntegerType(), False),
            ]))

        engaged_non_buyers = (
            prof_with_days.filter(F.col("valid_completed_order_count") == 0)
            .join(recent_counts, on="fan_id", how="inner")
            .filter(F.col("event_count") >= 1)
            .select(
                F.col("fan_id"),
                F.lit("engaged_non_buyers").alias("segment_code"),
                F.lit(1).alias("qualifies"),
                (F.col("marketing_consent_status") == "OPT_IN").cast("int").alias("activation_eligible"),
                F.concat(
                    F.lit("Has "),
                    F.col("event_count"),
                    F.lit(f" activity events in past {window_days}d and 0 completed orders.")
                ).alias("reason"),
            )
        )
        membership_rows.append(engaged_non_buyers)

        # 4. Inactive Fans (No activity in past 180 days relative to as_of)
        inact_cfg = rules_cfg.get("inactive_fans", {}).get("rules", {})
        inact_days = inact_cfg.get("inactivity_window_days", 180)
        inactive_fans = prof_with_days.filter(
            F.col("days_since_activity") > inact_days
        ).select(
            F.col("fan_id"),
            F.lit("inactive_fans").alias("segment_code"),
            F.lit(1).alias("qualifies"),
            (F.col("marketing_consent_status") == "OPT_IN").cast("int").alias("activation_eligible"),
            F.concat(
                F.lit("Last activity was "),
                F.col("days_since_activity"),
                F.lit(f" days ago (inactivity threshold: > {inact_days}d) or never active.")
            ).alias("reason"),
        )
        membership_rows.append(inactive_fans)

        # 5. Abandoned Cart (add_to_cart within 14d with matching session/cart, no resolving completed order)
        cart_cfg = rules_cfg.get("abandoned_cart", {}).get("rules", {})
        cart_window = cart_cfg.get("cart_window_days", 14)
        cutoff_cart = (self.as_of_dt - timedelta(days=cart_window)).strftime("%Y-%m-%dT%H:%M:%SZ")

        if web_df.count() > 0:
            # Qualifying cart additions
            cart_events = (
                web_df.filter(
                    (F.col("event_type") == "add_to_cart") &
                    (F.col("cart_id").isNotNull()) &
                    (F.col("cart_id") != "") &
                    (F.col("event_timestamp") >= F.lit(cutoff_cart)) &
                    (F.col("event_timestamp") <= F.lit(self.as_of_str))
                )
                .select(
                    F.col("fan_id"),
                    F.col("cart_id"),
                    F.col("event_timestamp").alias("cart_ts_str"),
                )
            )

            # Resolving orders (COMPLETED orders matching cart_id at or after cart addition)
            if orders_df.count() > 0:
                resolving_orders = (
                    orders_df.filter(
                        (F.col("order_status") == "COMPLETED") &
                        (F.col("cart_id").isNotNull()) &
                        (F.col("cart_id") != "")
                    )
                    .select(
                        F.col("fan_id"),
                        F.col("cart_id"),
                        F.col("order_timestamp").alias("order_ts_str"),
                    )
                )

                # Anti-join to find unresolved carts
                unresolved = cart_events.join(
                    resolving_orders,
                    on=["fan_id", "cart_id"],
                    how="left_anti"
                )
            else:
                unresolved = cart_events

            # Deduplicate by fan_id taking the latest unresolved cart
            win_cart = Window.partitionBy("fan_id").orderBy(F.col("cart_ts_str").desc())
            latest_unresolved = (
                unresolved.withColumn("rk", F.row_number().over(win_cart))
                .filter(F.col("rk") == 1)
                .withColumn("cart_ts", F.to_timestamp(F.col("cart_ts_str")))
                .withColumn(
                    "cart_age_days",
                    F.floor((F.unix_timestamp(as_of_ts) - F.unix_timestamp(F.col("cart_ts"))) / 86400).cast("int")
                )
            )

            abandoned_cart_members = (
                latest_unresolved.join(resolved_consent_df, on="fan_id", how="left")
                .select(
                    F.col("fan_id"),
                    F.lit("abandoned_cart").alias("segment_code"),
                    F.lit(1).alias("qualifies"),
                    F.coalesce(F.col("marketing_consent_status") == "OPT_IN", F.lit(False)).cast("int").alias("activation_eligible"),
                    F.concat(
                        F.lit("Unresolved cart "),
                        F.col("cart_id"),
                        F.lit(" created "),
                        F.col("cart_age_days"),
                        F.lit(" days ago without matching order.")
                    ).alias("reason"),
                )
            )
            membership_rows.append(abandoned_cart_members)

        # Union all memberships
        combined_memberships = membership_rows[0]
        for m_df in membership_rows[1:]:
            combined_memberships = combined_memberships.union(m_df)

        return combined_memberships
