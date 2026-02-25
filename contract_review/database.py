"""SQLite database for review persistence."""

import json
import sqlite3
from datetime import datetime

from .config import DB_PATH

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_name TEXT NOT NULL,
    date TEXT NOT NULL,
    reviewer TEXT DEFAULT '',
    status TEXT DEFAULT 'completed',
    analysis_mode TEXT DEFAULT 'hybrid',
    summary_json TEXT,
    metadata_json TEXT,
    flags_json TEXT
);

CREATE TABLE IF NOT EXISTS flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER NOT NULL,
    flag_id TEXT NOT NULL,
    classification TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    reviewer_action TEXT DEFAULT 'pending',
    reviewer_note TEXT DEFAULT '',
    reviewer_name TEXT DEFAULT '',
    action_timestamp TEXT,
    FOREIGN KEY (review_id) REFERENCES reviews(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rulebooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    version TEXT DEFAULT '1.0',
    uploaded_date TEXT NOT NULL,
    path TEXT NOT NULL
);
"""


def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(_CREATE_SQL)
    return db


def save_review(contract_name, analysis_mode, summary, metadata, flags, reviewer=""):
    db = get_db()
    cursor = db.execute(
        """INSERT INTO reviews (contract_name, date, reviewer, analysis_mode,
           summary_json, metadata_json, flags_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (contract_name, datetime.now().isoformat(), reviewer, analysis_mode,
         json.dumps(summary), json.dumps(metadata), json.dumps(flags)),
    )
    review_id = cursor.lastrowid
    for flag in flags:
        db.execute(
            "INSERT INTO flags (review_id, flag_id, classification, risk_level, confidence) VALUES (?, ?, ?, ?, ?)",
            (review_id, flag["flag_id"], flag["classification"], flag["risk_level"], flag.get("confidence", 0.5)),
        )
    db.commit()
    db.close()
    return review_id


def list_reviews():
    db = get_db()
    rows = db.execute(
        "SELECT id, contract_name, date, reviewer, status, analysis_mode FROM reviews ORDER BY date DESC"
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_review(review_id):
    db = get_db()
    row = db.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
    db.close()
    return dict(row) if row else None


def get_review_flags(review_id):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM flags WHERE review_id = ? ORDER BY flag_id", (review_id,)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def update_flag_action(review_id, flag_id, action, note="", reviewer_name=""):
    db = get_db()
    db.execute(
        "UPDATE flags SET reviewer_action=?, reviewer_note=?, reviewer_name=?, action_timestamp=? "
        "WHERE review_id=? AND flag_id=?",
        (action, note, reviewer_name, datetime.now().isoformat(), review_id, flag_id),
    )
    db.commit()
    db.close()


def bulk_update_flags(review_id, flag_ids, action, reviewer_name=""):
    db = get_db()
    now = datetime.now().isoformat()
    count = 0
    for fid in flag_ids:
        cursor = db.execute(
            "UPDATE flags SET reviewer_action=?, reviewer_name=?, action_timestamp=? "
            "WHERE review_id=? AND flag_id=?",
            (action, reviewer_name, now, review_id, fid),
        )
        count += cursor.rowcount
    db.commit()
    db.close()
    return count


def get_review_stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]

    avg_flags = 0.0
    common_deviations = {}
    if total > 0:
        rows = db.execute("SELECT flags_json FROM reviews").fetchall()
        total_flags = 0
        for row in rows:
            flags = json.loads(row["flags_json"])
            non_compliant = [f for f in flags if f.get("classification") != "compliant"]
            total_flags += len(non_compliant)
            for f in non_compliant:
                cls = f.get("classification", "unknown")
                common_deviations[cls] = common_deviations.get(cls, 0) + 1
        avg_flags = total_flags / total if total else 0.0

    db.close()
    return {
        "total_reviews": total,
        "avg_flags_per_contract": round(avg_flags, 1),
        "common_deviations": common_deviations,
    }


def get_rule_effectiveness():
    """Track which rules get triggered and how often they are rejected (false positives)."""
    db = get_db()
    rows = db.execute("SELECT flags_json FROM reviews").fetchall()
    flag_rows = db.execute(
        "SELECT flag_id, review_id, reviewer_action FROM flags WHERE reviewer_action != 'pending'"
    ).fetchall()

    # Build action lookup: (review_id, flag_id) -> action
    action_map = {}
    for fa in flag_rows:
        action_map[(fa["review_id"], fa["flag_id"])] = fa["reviewer_action"]

    rule_stats: dict[str, dict] = {}  # rule_id -> {triggered, accepted, rejected}

    review_rows = db.execute("SELECT id, flags_json FROM reviews").fetchall()
    for review_row in review_rows:
        review_id = review_row["id"]
        flags = json.loads(review_row["flags_json"])
        for flag in flags:
            for rule in flag.get("triggered_rules", []):
                rid = rule.get("rule_id", "unknown")
                if rid not in rule_stats:
                    rule_stats[rid] = {"rule_id": rid, "source": rule.get("source", ""),
                                       "clause": rule.get("clause", ""), "triggered": 0,
                                       "accepted": 0, "rejected": 0}
                rule_stats[rid]["triggered"] += 1
                action = action_map.get((review_id, flag["flag_id"]))
                if action == "accepted":
                    rule_stats[rid]["accepted"] += 1
                elif action == "rejected":
                    rule_stats[rid]["rejected"] += 1

    db.close()

    results = list(rule_stats.values())
    for r in results:
        total_reviewed = r["accepted"] + r["rejected"]
        r["false_positive_rate"] = round(r["rejected"] / total_reviewed, 2) if total_reviewed > 0 else 0.0
    results.sort(key=lambda x: -x["false_positive_rate"])
    return results
