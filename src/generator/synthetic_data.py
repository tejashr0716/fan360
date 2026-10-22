"""
Fan360 Synthetic Data Generator
Generates deterministic synthetic datasets for fictional motorsport team Apex Velocity Racing.
Includes configurable seed, volume, error rates, and defect injection tracking.
"""

from __future__ import annotations

import csv
import json
import os
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


FICTIONAL_DRIVERS = [
    "Elena Vance",
    "Marcus Lindholm",
    "Sofia Al-Mansoor",
    "Lucas Rossi",
]

COUNTRIES_LANGUAGES = [
    ("GBR", "en"),
    ("USA", "en"),
    ("ITA", "it"),
    ("FRA", "fr"),
    ("DEU", "de"),
    ("JPN", "ja"),
    ("BRA", "pt"),
    ("AUS", "en"),
    ("ESP", "es"),
    ("CAN", "en"),
]

FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Sam", "Chris", "Pat", "Riley",
    "Casey", "Cameron", "Avery", "Dakota", "Reese", "Quinn", "Skyler", "Rowan"
]

LAST_NAMES = [
    "Smith", "Vance", "Rossi", "Müller", "Dubois", "Tanaka", "Silva",
    "Ricci", "Weber", "Sato", "Moreau", "O'Connor", "Hansen", "Al-Mansoor"
]

WEB_EVENT_TYPES = ["page_view", "add_to_cart", "video_view", "telemetry_view"]
WEB_PAGES = [
    "/race-hub", "/live-telemetry", "/driver/elena-vance", "/driver/marcus-lindholm",
    "/store/team-cap", "/store/replica-jersey", "/store/diecast-model", "/store/jacket"
]

EMAIL_CAMPAIGNS = [
    "CMP_MONZA_PREVIEW_2026",
    "CMP_SILVERSTONE_RECAP_2026",
    "CMP_SEASON_LAUNCH_2026",
    "CMP_MERCH_SALE_SUMMER_2026",
]
EMAIL_ACTIONS = ["sent", "opened", "clicked"]


@dataclass
class InjectedDefect:
    defect_id: str
    source_table: str
    record_id: str
    defect_category: str
    defect_detail: str


@dataclass
class GeneratorManifest:
    dataset_name: str
    seed: int
    as_of_timestamp: str
    generated_at: str
    target_fans: int
    target_events: int
    defect_rate: float
    record_counts: Dict[str, int] = field(default_factory=dict)
    injected_defects: List[Dict[str, Any]] = field(default_factory=list)
    summary_by_defect_category: Dict[str, int] = field(default_factory=dict)


class SyntheticDataGenerator:
    """Deterministic synthetic data generator with defect injection."""

    def __init__(
        self,
        seed: int = 42,
        as_of_timestamp: str = "2026-10-01T00:00:00Z",
        defect_rate: float = 0.02,
    ):
        self.seed = seed
        self.defect_rate = defect_rate
        self.as_of_dt = datetime.fromisoformat(as_of_timestamp.replace("Z", "+00:00"))
        self.rng = random.Random(seed)
        self.injected_defects: List[InjectedDefect] = []

    def _random_timestamp_between(self, start_dt: datetime, end_dt: datetime) -> str:
        delta = end_dt - start_dt
        random_seconds = self.rng.randint(0, max(1, int(delta.total_seconds())))
        res = start_dt + timedelta(seconds=random_seconds)
        return res.strftime("%Y-%m-%dT%H:%M:%SZ")

    def generate_dataset(
        self,
        num_fans: int = 10000,
        num_events: int = 100000,
        dataset_name: str = "demo",
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], GeneratorManifest]:
        """Generates all 5 tables plus the generator manifest."""
        self.rng = random.Random(self.seed)
        self.injected_defects.clear()

        # Calculation windows
        start_history = self.as_of_dt - timedelta(days=365)

        # 1. Generate Fans
        fans: List[Dict[str, Any]] = []
        fan_ids: List[str] = []
        for i in range(1, num_fans + 1):
            fan_id = f"FAN_{i:06d}"
            fan_ids.append(fan_id)
            country, lang = self.rng.choice(COUNTRIES_LANGUAGES)
            first_name = self.rng.choice(FIRST_NAMES)
            last_name = self.rng.choice(LAST_NAMES)
            created_at = self._random_timestamp_between(start_history, self.as_of_dt - timedelta(days=30))

            fans.append({
                "fan_id": fan_id,
                "first_name": first_name,
                "last_name": last_name,
                "email": f"{first_name.lower()}.{last_name.lower()}_{i}@fictional-fans.net",
                "country": country,
                "language": lang,
                "preferred_driver": self.rng.choice(FICTIONAL_DRIVERS),
                "created_at": created_at,
            })

        # Determine target distribution for events
        # Approximate: 50% web events, 30% email events, 10% orders, 10% consents
        target_web = int(num_events * 0.50)
        target_email = int(num_events * 0.30)
        target_orders = int(num_events * 0.10)
        target_consents = int(num_events * 0.10)

        # 2. Generate Orders
        orders: List[Dict[str, Any]] = []
        # Pre-assign buyer categories to create realistic distributions:
        # 15% repeat buyers, 20% single buyers, 65% non-buyers
        buyer_fans = self.rng.sample(fan_ids, k=int(num_fans * 0.35))
        repeat_buyer_fans = set(buyer_fans[: int(num_fans * 0.15)])
        single_buyer_fans = set(buyer_fans[int(num_fans * 0.15):])

        order_id_counter = 1
        for f_id in buyer_fans:
            count = self.rng.randint(2, 6) if f_id in repeat_buyer_fans else 1
            for _ in range(count):
                order_id = f"ORD_{order_id_counter:07d}"
                order_id_counter += 1
                status = self.rng.choices(
                    ["COMPLETED", "CANCELLED", "REFUNDED", "PENDING"],
                    weights=[0.85, 0.05, 0.05, 0.05]
                )[0]
                amount = round(self.rng.uniform(25.0, 180.0), 2)
                order_dt = self._random_timestamp_between(start_history, self.as_of_dt)
                items_cnt = self.rng.randint(1, 5)

                orders.append({
                    "order_id": order_id,
                    "fan_id": f_id,
                    "order_status": status,
                    "order_amount": amount,
                    "currency": "USD",
                    "order_timestamp": order_dt,
                    "items_count": items_cnt,
                    "cart_id": f"CART_{self.rng.randint(1, 50000):06d}",
                })

        # Fill orders if below target
        while len(orders) < target_orders:
            order_id = f"ORD_{order_id_counter:07d}"
            order_id_counter += 1
            f_id = self.rng.choice(fan_ids)
            orders.append({
                "order_id": order_id,
                "fan_id": f_id,
                "order_status": "COMPLETED",
                "order_amount": round(self.rng.uniform(20.0, 120.0), 2),
                "currency": "USD",
                "order_timestamp": self._random_timestamp_between(start_history, self.as_of_dt),
                "items_count": self.rng.randint(1, 3),
                "cart_id": f"CART_{self.rng.randint(1, 50000):06d}",
            })

        # 3. Generate Web Events
        web_events: List[Dict[str, Any]] = []
        for i in range(1, target_web + 1):
            event_id = f"WEB_{i:07d}"
            f_id = self.rng.choice(fan_ids)
            session_id = f"SESS_{self.rng.randint(1, target_web // 3):07d}"
            event_type = self.rng.choices(WEB_EVENT_TYPES, weights=[0.60, 0.15, 0.15, 0.10])[0]
            cart_id = f"CART_{self.rng.randint(1, 50000):06d}" if event_type == "add_to_cart" else ""
            event_dt = self._random_timestamp_between(start_history, self.as_of_dt)

            web_events.append({
                "event_id": event_id,
                "fan_id": f_id,
                "session_id": session_id,
                "event_type": event_type,
                "event_timestamp": event_dt,
                "page_url": self.rng.choice(WEB_PAGES),
                "cart_id": cart_id,
            })

        # 4. Generate Email Events
        email_events: List[Dict[str, Any]] = []
        for i in range(1, target_email + 1):
            event_id = f"EML_{i:07d}"
            f_id = self.rng.choice(fan_ids)
            campaign_id = self.rng.choice(EMAIL_CAMPAIGNS)
            action = self.rng.choices(EMAIL_ACTIONS, weights=[0.60, 0.30, 0.10])[0]
            event_dt = self._random_timestamp_between(start_history, self.as_of_dt)

            email_events.append({
                "event_id": event_id,
                "fan_id": f_id,
                "campaign_id": campaign_id,
                "action": action,
                "event_timestamp": event_dt,
            })

        # 5. Generate Consent Records
        # Standard: 70% fans have OPT_IN, 20% OPT_OUT, 10% no record / multiple records
        consents: List[Dict[str, Any]] = []
        consent_id_counter = 1
        for f_id in fan_ids:
            # 10% chance no initial consent (missing consent)
            if self.rng.random() < 0.10:
                continue

            status = "OPT_IN" if self.rng.random() < 0.75 else "OPT_OUT"
            c_dt = self._random_timestamp_between(start_history, self.as_of_dt - timedelta(days=10))
            consents.append({
                "consent_id": f"CNS_{consent_id_counter:07d}",
                "fan_id": f_id,
                "consent_type": "marketing_email",
                "status": status,
                "update_timestamp": c_dt,
                "channel": self.rng.choice(["web_form", "account_settings"]),
            })
            consent_id_counter += 1

            # 15% chance fan updated consent later (withdrawal or opt-in)
            if self.rng.random() < 0.15:
                new_status = "OPT_OUT" if status == "OPT_IN" else "OPT_IN"
                update_dt = self._random_timestamp_between(
                    datetime.fromisoformat(c_dt.replace("Z", "+00:00")),
                    self.as_of_dt
                )
                consents.append({
                    "consent_id": f"CNS_{consent_id_counter:07d}",
                    "fan_id": f_id,
                    "consent_type": "marketing_email",
                    "status": new_status,
                    "update_timestamp": update_dt,
                    "channel": "unsubscribe_link" if new_status == "OPT_OUT" else "account_settings",
                })
                consent_id_counter += 1

        # 6. Inject Representative Defects (Controlled & Ground-Truthed)
        if self.defect_rate > 0.0:
            self._inject_defects(fans, orders, web_events, email_events, consents)

        # Build Manifest
        defect_summary: Dict[str, int] = {}
        for d in self.injected_defects:
            defect_summary[d.defect_category] = defect_summary.get(d.defect_category, 0) + 1

        manifest = GeneratorManifest(
            dataset_name=dataset_name,
            seed=self.seed,
            as_of_timestamp=self.as_of_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            target_fans=num_fans,
            target_events=num_events,
            defect_rate=self.defect_rate,
            record_counts={
                "fans": len(fans),
                "orders": len(orders),
                "web_events": len(web_events),
                "email_events": len(email_events),
                "consent": len(consents),
            },
            injected_defects=[asdict(d) for d in self.injected_defects],
            summary_by_defect_category=defect_summary,
        )

        data = {
            "fans": fans,
            "orders": orders,
            "web_events": web_events,
            "email_events": email_events,
            "consent": consents,
        }
        return data, manifest

    def _inject_defects(
        self,
        fans: List[Dict[str, Any]],
        orders: List[Dict[str, Any]],
        web_events: List[Dict[str, Any]],
        email_events: List[Dict[str, Any]],
        consents: List[Dict[str, Any]],
    ) -> None:
        """Injects representative defects across datasets with exact ground-truth recording."""
        defect_idx = 1

        # 1. Duplicate Event IDs in Web Events
        num_web_dups = max(5, int(len(web_events) * self.defect_rate * 0.25))
        for _ in range(num_web_dups):
            source_rec = self.rng.choice(web_events)
            dup_rec = dict(source_rec)
            # Duplicate ID, identical or slightly different timestamp
            web_events.append(dup_rec)
            self.injected_defects.append(InjectedDefect(
                defect_id=f"DEF_{defect_idx:06d}",
                source_table="web_events",
                record_id=dup_rec["event_id"],
                defect_category="DUPLICATE_ID",
                defect_detail=f"Duplicate event_id {dup_rec['event_id']}",
            ))
            defect_idx += 1

        # 2. Missing Required Identifiers (e.g. Null fan_id or Null event_id)
        num_missing = max(5, int(len(orders) * self.defect_rate * 0.20))
        for _ in range(num_missing):
            target = self.rng.choice(orders)
            field_to_corrupt = self.rng.choice(["fan_id", "order_id"])
            target[field_to_corrupt] = ""
            self.injected_defects.append(InjectedDefect(
                defect_id=f"DEF_{defect_idx:06d}",
                source_table="orders",
                record_id=target.get("order_id") or "UNKNOWN_ORDER_ID",
                defect_category="MISSING_REQUIRED_FIELD",
                defect_detail=f"Field {field_to_corrupt} was set to empty/null",
            ))
            defect_idx += 1

        # 3. Invalid Timestamps (Future timestamp beyond as_of or corrupted date string)
        num_invalid_dates = max(5, int(len(email_events) * self.defect_rate * 0.20))
        for _ in range(num_invalid_dates):
            target = self.rng.choice(email_events)
            # Either future date or malformed string
            if self.rng.random() < 0.5:
                future_dt = self.as_of_dt + timedelta(days=120)
                target["event_timestamp"] = future_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                detail = "Timestamp is in future relative to as_of date"
            else:
                target["event_timestamp"] = "INVALID_TIMESTAMP_STRING_9999"
                detail = "Malformed timestamp string"

            self.injected_defects.append(InjectedDefect(
                defect_id=f"DEF_{defect_idx:06d}",
                source_table="email_events",
                record_id=target["event_id"],
                defect_category="INVALID_TIMESTAMP",
                defect_detail=detail,
            ))
            defect_idx += 1

        # 4. Unknown Fan Reference (Orphan event referencing non-existent fan)
        num_unknown_fans = max(5, int(len(web_events) * self.defect_rate * 0.20))
        for _ in range(num_unknown_fans):
            target = self.rng.choice(web_events)
            orphan_id = f"FAN_NONEXISTENT_{self.rng.randint(900000, 999999)}"
            target["fan_id"] = orphan_id
            self.injected_defects.append(InjectedDefect(
                defect_id=f"DEF_{defect_idx:06d}",
                source_table="web_events",
                record_id=target["event_id"],
                defect_category="UNKNOWN_FAN_REFERENCE",
                defect_detail=f"Event references non-existent fan {orphan_id}",
            ))
            defect_idx += 1

        # 5. Invalid Order Amounts (Negative or zero order amount)
        num_bad_orders = max(5, int(len(orders) * self.defect_rate * 0.20))
        for _ in range(num_bad_orders):
            target = self.rng.choice(orders)
            target["order_amount"] = -1 * round(self.rng.uniform(10.0, 99.0), 2)
            self.injected_defects.append(InjectedDefect(
                defect_id=f"DEF_{defect_idx:06d}",
                source_table="orders",
                record_id=target["order_id"],
                defect_category="INVALID_ORDER_AMOUNT",
                defect_detail=f"Order amount is negative ({target['order_amount']})",
            ))
            defect_idx += 1

        # 6. Conflicting or Invalid Consent Status (e.g. status='MAYBE')
        num_bad_consents = max(5, int(len(consents) * self.defect_rate * 0.15))
        for _ in range(num_bad_consents):
            target = self.rng.choice(consents)
            target["status"] = "MAYBE"
            self.injected_defects.append(InjectedDefect(
                defect_id=f"DEF_{defect_idx:06d}",
                source_table="consent",
                record_id=target["consent_id"],
                defect_category="INVALID_CONSENT_STATUS",
                defect_detail="Consent status has invalid value 'MAYBE'",
            ))
            defect_idx += 1


def export_dataset_to_csv(
    data: Dict[str, List[Dict[str, Any]]],
    manifest: GeneratorManifest,
    output_dir: str,
) -> None:
    """Exports generated tables to CSV and manifest to JSON."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    for table_name, records in data.items():
        if not records:
            continue
        file_path = out_path / f"{table_name}.csv"
        headers = list(records[0].keys())
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(records)

    # Save manifest separately
    manifest_path = out_path / "generator_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(asdict(manifest), f, indent=2)
