"""
models/history.py
=================
HistoryManager class — stores and retrieves scan results per user
in the MongoDB Atlas 'scan_history' collection.

Document schema (scan_history collection)
──────────────────────────────────────────
{
    "_id":            ObjectId,          # auto-generated
    "user_id":        str,               # User._id (string form of ObjectId)
    "url":            str,               # URL of the scanned page
    "scanned_at":     datetime (UTC),    # timestamp
    "score":          int,               # credibility score 0–100
    "verdict":        str,               # "Credible" | "Uncertain" | "Likely Fake"
    "color":          str,               # "green" | "amber" | "red"
    "probability":    float,             # raw model output (fake probability)
    "summary":        str,               # credibility assessment paragraph
    "content_summary":str,               # extractive article summary
    "signals": [                         # list of signal objects
        {
            "type":    str,              # "ok" | "warn" | "bad"
            "label":   str,
            "detail":  str,
            "snippet": str
        },
        ...
    ]
}

Indexes created automatically
──────────────────────────────
- { user_id: 1, scanned_at: -1 }  ← fast per-user history queries
"""

from datetime import datetime, timezone
from pymongo import MongoClient, DESCENDING
from bson import ObjectId

from config import MONGO_URI


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE CONNECTION (shared with user.py via same URI)
# ─────────────────────────────────────────────────────────────────────────────
_client = MongoClient(MONGO_URI)
_db     = _client["factguard"]


class HistoryManager:
    """
    Manages scan history records for FactGuard users.

    All methods are instance methods operating on self.user_id,
    so one HistoryManager instance = one user's history context.

    Usage
    ─────
        hm = HistoryManager(user_id="64abc...")
        hm.save_scan(url, result_dict)
        recent = hm.get_recent(limit=5)
    """

    collection = _db["scan_history"]

    # Compound index: fast lookup of a user's scans sorted by newest first
    collection.create_index(
        [("user_id", 1), ("scanned_at", DESCENDING)]
    )

    def __init__(self, user_id: str):
        """
        Parameters
        ──────────
        user_id : str
            The string representation of the authenticated user's MongoDB _id.
        """
        self.user_id = str(user_id)

    # ── Save a scan ───────────────────────────────────────────────────────────

    def save_scan(self, url: str, result: dict) -> str:
        """
        Persist a completed scan result to MongoDB.

        Parameters
        ──────────
        url    : str   The URL of the scanned page (passed from the extension).
        result : dict  The full result dict built by build_signals / build_assessment
                       in server.py. Expected keys:
                           score, verdict, color, probability,
                           summary, content_summary, signals

        Returns
        ───────
        str : The inserted document's _id (string form).
        """
        doc = {
            "user_id":         self.user_id,
            "url":             url,
            "scanned_at":      datetime.now(timezone.utc),
            "score":           result.get("score",           0),
            "verdict":         result.get("verdict",         ""),
            "color":           result.get("color",           ""),
            "probability":     result.get("probability",     0.0),
            "summary":         result.get("summary",         ""),
            "content_summary": result.get("content_summary", ""),
            "signals":         result.get("signals",         []),
        }
        inserted = self.collection.insert_one(doc)
        return str(inserted.inserted_id)

    # ── Retrieve recent scans ─────────────────────────────────────────────────

    def get_recent(self, limit: int = 5) -> list[dict]:
        """
        Return the most recent `limit` scans for this user,
        newest first, serialised as plain dicts safe for JSON.

        Parameters
        ──────────
        limit : int   Maximum number of records to return (default 5).

        Returns
        ───────
        list[dict] : Each dict contains:
            id, url, scanned_at (ISO string), score, verdict, color,
            probability, summary, content_summary, signals
        """
        cursor = (
            self.collection
            .find({"user_id": self.user_id})
            .sort("scanned_at", DESCENDING)
            .limit(limit)
        )
        return [self._serialise(doc) for doc in cursor]

    # ── Delete a single scan ──────────────────────────────────────────────────

    def delete_scan(self, scan_id: str) -> bool:
        """
        Delete a scan record by its _id.
        Returns True if a document was deleted, False otherwise.
        """
        result = self.collection.delete_one({
            "_id":     ObjectId(scan_id),
            "user_id": self.user_id,   # enforce ownership
        })
        return result.deleted_count == 1

    # ── Clear all scans for this user ─────────────────────────────────────────

    def clear_history(self) -> int:
        """Delete all scan records for this user. Returns count deleted."""
        result = self.collection.delete_many({"user_id": self.user_id})
        return result.deleted_count

    # ── Private: serialise a MongoDB doc ─────────────────────────────────────

    @staticmethod
    def _serialise(doc: dict) -> dict:
        """Convert a raw MongoDB document to a JSON-safe dict."""
        scanned_at = doc.get("scanned_at")
        return {
            "id":              str(doc["_id"]),
            "url":             doc.get("url", ""),
            "scanned_at":      scanned_at.isoformat() if scanned_at else "",
            "score":           doc.get("score",           0),
            "verdict":         doc.get("verdict",         ""),
            "color":           doc.get("color",           ""),
            "probability":     doc.get("probability",     0.0),
            "summary":         doc.get("summary",         ""),
            "content_summary": doc.get("content_summary", ""),
            "signals":         doc.get("signals",         []),
        }
