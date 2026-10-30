"""Small transactional source registry; personal conversations are opt-in writes."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "app.sqlite"
        with self.db() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, info TEXT, active TEXT);
              CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY, source_id TEXT, hash TEXT,
                created TEXT, status TEXT, note TEXT, audit TEXT, path TEXT);
              CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY, version_id TEXT, info TEXT);
              CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY, hcp_id TEXT, created TEXT, info TEXT);
              CREATE TABLE IF NOT EXISTS deliveries(hcp_id TEXT, version_id TEXT, created TEXT,
                PRIMARY KEY(hcp_id, version_id));
              CREATE TABLE IF NOT EXISTS conversation_summaries(hcp_id TEXT PRIMARY KEY, updated TEXT, info TEXT);
            """)
            if "source_snapshot" not in {r["name"] for r in db.execute("PRAGMA table_info(versions)")}:
                db.execute("ALTER TABLE versions ADD COLUMN source_snapshot TEXT")
                db.execute("UPDATE versions SET source_snapshot=(SELECT info FROM sources WHERE id=source_id)")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, sources):
        with self.db() as db:
            for source in sources:
                db.execute("INSERT INTO sources(id,info) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET info=excluded.info",
                           (source["id"], json.dumps(source)))

    def stage(self, source, version, content_hash, chunks, audit, path):
        with self.db() as db:
            exists = db.execute("SELECT status FROM versions WHERE id=?", (version,)).fetchone()
            if exists:
                return exists["status"]
            db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?,?,?)",
                       (version, source["id"], content_hash, now(), "staged", "", json.dumps(audit), str(path),
                        json.dumps(source)))
            for index, chunk in enumerate(chunks):
                cid = f"{version}:{index}"
                db.execute("INSERT INTO chunks VALUES(?,?,?)", (cid, version, json.dumps(chunk)))
        return "staged"

    def versions(self):
        with self.db() as db:
            rows = db.execute("SELECT v.*,s.info AS source_info FROM versions v JOIN sources s ON s.id=v.source_id "
                              "ORDER BY v.created DESC").fetchall()
        return [{**dict(r), "source": json.loads(r["source_snapshot"]), "audit": json.loads(r["audit"])} for r in rows]

    def activate(self, version, note):
        if not note.strip():
            raise ValueError("A review note is required.")
        with self.db() as db:
            row = db.execute("SELECT v.*,s.info FROM versions v JOIN sources s ON s.id=v.source_id WHERE v.id=?",
                             (version,)).fetchone()
            if not row or not eligible(json.loads(row["info"]), allow_account=True):
                raise ValueError("Source is not eligible for the German HCP prototype.")
            if not db.execute("SELECT 1 FROM chunks WHERE version_id=?", (version,)).fetchone():
                raise ValueError("No usable chunks; review extraction first.")
            db.execute("UPDATE versions SET status='superseded' WHERE source_id=? AND status='active'",
                       (row["source_id"],))
            db.execute("UPDATE versions SET status='active',note=? WHERE id=?", (note, version))
            db.execute("UPDATE sources SET active=? WHERE id=?", (version, row["source_id"]))

    def deactivate(self, version):
        with self.db() as db:
            db.execute("UPDATE sources SET active=NULL WHERE active=?", (version,))
            db.execute("UPDATE versions SET status='withdrawn' WHERE id=?", (version,))

    def version_chunks(self, version):
        """Eligible staged passages for indexing; never used by chat before activation."""
        with self.db() as db:
            rows = db.execute("SELECT c.id,c.version_id,c.info,s.info AS source_info,v.source_snapshot "
                              "FROM chunks c JOIN versions v ON v.id=c.version_id "
                              "JOIN sources s ON s.id=v.source_id WHERE v.id=?", (version,)).fetchall()
        return [{**json.loads(r["info"]), "id": r["id"], "version_id": r["version_id"],
                 "source": json.loads(r["source_snapshot"])} for r in rows
                if eligible(json.loads(r["source_info"]), allow_account=True)
                and eligible(json.loads(r["source_snapshot"]), allow_account=True)
                and within_pages(json.loads(r["info"]), json.loads(r["source_info"]))]

    def chunks(self, account_id=None, all_accounts=False):
        with self.db() as db:
            rows = db.execute("SELECT c.id,c.version_id,c.info,s.info AS source_info,v.source_snapshot FROM chunks c "
                              "JOIN versions v ON v.id=c.version_id JOIN sources s ON s.active=v.id "
                              "WHERE v.status='active'").fetchall()
        return [{**json.loads(r["info"]), "id": r["id"], "version_id": r["version_id"],
                 "source": json.loads(r["source_snapshot"])} for r in rows
                if eligible(json.loads(r["source_info"]), account_id, allow_account=all_accounts)
                and eligible(json.loads(r["source_snapshot"]), account_id, allow_account=all_accounts)
                and within_pages(json.loads(r["info"]), json.loads(r["source_info"]))
                and within_pages(json.loads(r["info"]), json.loads(r["source_snapshot"]))]

    def history(self, hcp_id):
        if not hcp_id:
            return []
        with self.db() as db:
            rows = db.execute("SELECT info FROM chats WHERE hcp_id=? ORDER BY id DESC", (hcp_id,)).fetchall()
        return [json.loads(r["info"]) for r in reversed(rows)]

    def conversation_history(self, hcp_id):
        """All consented turns with stable message IDs and UTC timestamps; no retention truncation."""
        with self.db() as db:
            rows = db.execute("SELECT id,created,info FROM chats WHERE hcp_id=? ORDER BY id", (hcp_id,)).fetchall()
        messages = []
        for row in rows:
            record = json.loads(row["info"])
            for role, field in (("user", "question"), ("assistant", "answer")):
                if field not in record:
                    continue
                message = {"id": record.get(field + "_id", f"saved:{row['id']}:{role}"),
                    "timestamp": record.get(field + "_timestamp", row["created"]),
                    "hcp_id": hcp_id, "role": role, "content": record[field]}
                if role == "assistant":
                    message["policy_route"] = record.get("policy_route")
                    message["result"] = {"answer": record[field], "decision": record.get("decision", "answer"),
                        "citations": record.get("citations", []), "context_used": {}, "warnings": [],
                        "limitations": [], "handoff": record.get("handoff"), "policy_route": record.get("policy_route")}
                messages.append(message)
        return messages

    def conversation_state(self, hcp_id):
        with self.db() as db:
            row = db.execute("SELECT info FROM conversation_summaries WHERE hcp_id=?", (hcp_id,)).fetchone()
        return json.loads(row["info"]) if row else {}

    def save_conversation_state(self, hcp_id, state, consent=False):
        if hcp_id and consent:
            if state.get("hcp_id") != hcp_id:
                raise ValueError("Cannot save another HCP's working summary.")
            # Turning storage on later does not grant retrospective storage consent.
            recorded = {m["id"] for m in self.conversation_history(hcp_id)}
            covered = state.get("covered_message_ids", [])
            if len(covered) != state.get("covered_count", 0) or not set(covered) <= recorded:
                return False
            with self.db() as db:
                db.execute("INSERT INTO conversation_summaries VALUES(?,?,?) ON CONFLICT(hcp_id) DO UPDATE "
                           "SET updated=excluded.updated,info=excluded.info", (hcp_id, now(), json.dumps(state)))
            return True
        return False

    def remember(self, hcp_id, record, consent=False):
        if hcp_id and consent:
            with self.db() as db:
                db.execute("INSERT INTO chats(hcp_id,created,info) VALUES(?,?,?)",
                           (hcp_id, now(), json.dumps(record, ensure_ascii=False)))

    def delete_history(self, hcp_id):
        with self.db() as db:
            db.execute("DELETE FROM chats WHERE hcp_id=?", (hcp_id,))
            db.execute("DELETE FROM deliveries WHERE hcp_id=?", (hcp_id,))
            db.execute("DELETE FROM conversation_summaries WHERE hcp_id=?", (hcp_id,))

    def delivered(self, hcp_id, version, consent=False):
        if not hcp_id or not consent:
            return False
        with self.db() as db:
            cursor = db.execute("INSERT OR IGNORE INTO deliveries VALUES(?,?,?)", (hcp_id, version, now()))
        return cursor.rowcount == 1


def eligible(source, account_id=None, allow_account=False):
    today = datetime.now(timezone.utc).date().isoformat()
    return (source.get("eligible") is True and source.get("market") in {"DE", "EU"}
            and source.get("audience") == "HCP"
            and (not source.get("valid_from") or source["valid_from"] <= today)
            and (not source.get("valid_to") or source["valid_to"] >= today)
            and (not source.get("account_id") or allow_account or source["account_id"] == account_id))


def within_pages(chunk, source):
    start, end = source.get("pages", [1, 100000])
    first, last = chunk.get("page", 1), chunk.get("page_end", chunk.get("page", 1))
    return start <= first <= last <= end and not any(first <= p <= last for p in source.get("review_pages", []))
