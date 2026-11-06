"""The sixteen user-specified rules; retrieval eligibility and escalation metadata."""
import re
from datetime import datetime, timezone

RULES = {
    "GR_01": ("Off-label question detected", "Block generation; issue MI referral message", "Medical Information"),
    "GR_02": ("Adverse event mentioned", "Answer suppressed; AE intake path triggered; log within 24h", "Pharmacovigilance"),
    "GR_03": ("Product complaint mentioned", "Route to QA intake", "Quality"),
    "GR_04": ("Individual patient advice", "Decline individualised advice; offer MSL", "MSL"),
    "GR_05": ("Comparative claim requested", "No comparison generated; offer approved evidence + MSL", "MSL"),
    "GR_06": ("Content expired", "Exclude from retrieval", None),
    "GR_07": ("Content not approved", "Exclude from retrieval", None),
    "GR_08": ("Audience mismatch", "Exclude from retrieval", None),
    "GR_09": ("Market mismatch", "Exclude from retrieval", None),
    "GR_10": ("Promotional / medical boundary", "Restrict to medical sources; flag for review", "Medical"),
    "GR_11": ("No approved source above threshold", "Decline to answer; offer human", "Rep or MSL"),
    "GR_12": ("Proactive outbound without consent", "Suppress proactive message", None),
    "GR_13": ("Confidential insight", "Exclude from signal layer entirely", None),
    "GR_14": ("Human explicitly requested", "Immediate handoff with summary", "Rep or MSL"),
    "GR_15": ("Low answer confidence", "Ask clarifying question or escalate", "Rep or MSL"),
    "GR_16": ("Audit trail", "Persist question, sources, decision, user, timestamp", None),
}

ROUTES = {"off_label": "GR_01", "adverse_event": "GR_02", "complaint": "GR_03",
          "patient": "GR_04", "comparison": "GR_05", "medical_boundary": "GR_10",
          "insufficient": "GR_11", "proactive": "GR_12", "privacy": "GR_13",
          "human": "GR_14", "validation": "GR_15", "low_confidence": "GR_15",
          "scope_uncertain": "GR_15"}


def metadata(rule_id):
    trigger, action, target = RULES[rule_id]
    return {"rule_id": rule_id, "trigger": trigger, "action": action, "escalation_target": target}


def source_rules(source, cfg, account_id=None):
    """Return every applicable exclusion. Registry eligibility is prototype approval metadata."""
    today = datetime.now(timezone.utc).date().isoformat()
    rules = []
    if source.get("valid_to") and source["valid_to"] < today:
        rules.append("GR_06")
    if (source.get("eligible") is not True or source.get("approved") is False
            or source.get("status") in {"withdrawn", "superseded", "staged"}
            or source.get("valid_from") and source["valid_from"] > today):
        rules.append("GR_07")
    if source.get("audience") != cfg.get("audience", "HCP"):
        rules.append("GR_08")
    market = cfg.get("market", "DE")
    if source.get("market") not in ({"DE", "EU"} if market == "DE" else {market}):
        rules.append("GR_09")
    if source.get("account_id") and source["account_id"] != account_id:
        rules.append("GR_13")
    if cfg.get("medical_only") and not medical_source(source):
        rules.append("GR_10")
    return rules


def medical_source(source):
    return source.get("medical") is True or (source.get("medical") is not False
        and source.get("kind") in {"label", "risk_management", "publication", "medical"})


def confidential(value):
    if isinstance(value, dict):
        if any(str(value.get(key, "")).lower() in {"true", "yes", "1", "confidential", "restricted"}
               for key in ("confidential", "is_confidential", "confidentiality", "sensitivity")):
            return True
        return any(confidential(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(confidential(item) for item in value)
    return isinstance(value, str) and bool(re.search(r"\bconfidential\b|\bvertraulich\b|\boff the record\b", value, re.I))


def outbound_consent(hcp):
    return bool(hcp) and str(hcp.get("proactive_outbound_consent",
        hcp.get("consent_proactive", hcp.get("proactive_consent", "")))).lower() in {"true", "yes", "1"}


def above_threshold(cfg, passages):
    if not cfg.get("reranking_enabled"):
        return [p for p in passages if p.get("retrieval", {}).get("keyword_matches", 0)
                >= cfg.get("retrieval_min_keyword_matches", 1)]
    return [p for p in passages if p.get("retrieval", {}).get("relevance", -1)
            >= cfg.get("retrieval_min_relevance", 2)]
