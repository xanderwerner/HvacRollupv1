"""SQLite working store (staging — NOT the master Excel)."""
import sqlite3
from typing import Iterable

import config
from models import Lead

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    place_id TEXT PRIMARY KEY,
    company_name TEXT, trade_type TEXT, city TEXT, discovery_source TEXT,
    business_address TEXT, website TEXT, business_phone TEXT, business_status TEXT,
    review_count INTEGER, rating REAL,
    research_stage TEXT, disqualify_reason TEXT,
    buy_box_fit TEXT, priority_tier TEXT, survived_filter INTEGER
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(_SCHEMA)
    return conn


def upsert(conn: sqlite3.Connection, leads: Iterable[Lead]) -> int:
    n = 0
    for lead in leads:
        d = lead.as_dict()
        d["survived_filter"] = int(d["survived_filter"])
        cols = ",".join(d.keys())
        ph = ",".join("?" for _ in d)
        conn.execute(
            f"INSERT OR REPLACE INTO leads ({cols}) VALUES ({ph})", list(d.values())
        )
        n += 1
    conn.commit()
    return n
