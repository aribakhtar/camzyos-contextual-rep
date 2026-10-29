"""Deterministic workbook import: clinical placeholder text is never an evidence source."""
from datetime import date, datetime
from io import BytesIO

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel


def load_profiles(path) -> dict[str, list[dict]]:
    # BytesIO avoids keeping Excel files open after loading.
    book = load_workbook(BytesIO(path.read_bytes()), read_only=True, data_only=True)
    tables = {}
    for sheet in book:
        rows = list(sheet.values)
        if not rows:
            continue
        # Some workbook sheets have a title or introductory rows before the field names.
        start = next((i for i, row in enumerate(rows[:12]) if "hcp_id" in row or
                      any(v in row for v in ("rule_id", "gap_id", "intent_id", "local_context_id"))), 0)
        headers = [str(x).strip() if x is not None else "" for x in rows[start]]
        entries = []
        for number, row in enumerate(rows[start + 1:], start + 2):
            if not any(v is not None for v in row):
                continue
            item = {k: clean(v, k) for k, v in zip(headers, row) if k}
            item["_row"] = number
            entries.append(item)
        tables[sheet.title] = entries
    book.close()
    return tables


def clean(value, key=""):
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if "date" in key.lower() and isinstance(value, (int, float)) and value > 20000:
        return from_excel(value).date().isoformat()
    return str(value).strip()


def resolve_hcp(tables, email: str) -> dict | None:
    return next((p for p in tables.get("HCP_Profile", [])
                 if p.get("email", "").casefold() == email.strip().casefold()), None)


PROFILE_FIELDS = ("name", "specialty", "sub_specialty", "yearsExperience", "market", "language",
                  "workplace", "camzyos_experience", "communicationStyle", "keyConcerns",
                  "shared_by_hcp", "topics_discussed", "previous_questions", "content_already_received",
                  "last_interaction_date", "preferred_channel", "safetyPreference")


def context(tables: dict, hcp: dict | None) -> dict:
    if not hcp:
        return {}
    identity = hcp["hcp_id"]
    return {
        "profile": {k: hcp.get(k, "") for k in PROFILE_FIELDS},
        "profile_record": identity,
        "personality": [p for p in tables.get("Personality", []) if p.get("hcp_id") == identity],
        "interactions": sorted(
            [p for p in tables.get("HCP_Interactions", []) if p.get("hcp_id") == identity],
            key=lambda p: p.get("date", p.get("interaction_date", "")), reverse=True,
        )[:8],
    }
