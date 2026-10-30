"""Conservative intent checks; no medical facts or regulatory decisions are inferred here."""
import re

SYMPTOMS = (r"faint(?:ed|ing)?|syncope|breathless(?:ness)?|short(?:ness)? of breath|dyspn(?:oe|e)a|"
            r"(?:leg )?(?:swelling|oedema|edema)|dizz(?:y|iness)|palpitations|chest pain|rash|"
            r"kurzatmig\w*|atemnot|ohnmacht|ohnm[äa]chtig|schwindel|(?:bein)?[öo]dem\w*|ausschlag")
EXPOSURE = r"after|since|following|during|started|starting|began|taking|dose|treatment|camzyos|mavacamten|nach|seit|beginn|dosis|behandlung|einnahme"
OCCURRENCE = r"became|developed|reports?|reported|has|had|fainted|now|experienced|wurde|bekam|entwickelt\w*|berichtet|hat|hatte|aufgetreten|ohnm[äa]chtig"
SCOPE = (r"\b(?:off[- ]label|non[- ]obstructive|nicht[- ]obstruktiv\w*|pa?ediatric|children|"
         r"child(?![- ]Pugh)|kinder\w*|HFpEF|HFrEF|amyloid\w*)\b")


def negated_prefix(text, start):
    prefix = re.split(r"[.;!?]|\bbut\b|\baber\b", text[:start], flags=re.I)[-1][-110:]
    return bool(re.search(r"(?:\bno\b|\bnot\b|\bnever\b|\bdenies\b|\bwithout\b|\bnicht\b|\bkein\w*)"
                          r"(?:[\s,'’-]+\w+){0,5}[\s,'’-]*$", prefix, re.I))


def reported_event(question, history=()):
    if re.search(r"report (?:an? )?(?:adverse event|side effect)|adverse event report|nebenwirkung melden", question, re.I):
        return True
    for clause in re.split(r"[;!?]|\bbut\b|\baber\b", question, flags=re.I):
        if re.search(r"\bhypothetical\w*|\bsuppose\b|\bif a patient\b|\bangenommen\b|\bhypothetisch\w*", clause, re.I):
            continue
        symptoms = [m for m in re.finditer(SYMPTOMS, clause, re.I) if not negated_prefix(clause, m.start())]
        if not symptoms or not re.search(OCCURRENCE, clause, re.I):
            continue
        subject = re.search(r"\bpatient\w*|\bsomeone\b|\bperson\b", question, re.I)
        previous = " ".join(row.get("content", "") for row in history if row.get("role") == "user")
        referred_subject = re.search(r"\b(?:she|he|they|her|him|sie|er)\b", clause, re.I) and re.search(r"patient", previous, re.I)
        if (subject or referred_subject) and (re.search(EXPOSURE, clause, re.I)
                                            or referred_subject and re.search(EXPOSURE, previous, re.I)):
            return True
    return False


def scope_signal(question):
    """A scope keyword alone in a negated instruction must not trigger an off-label refusal."""
    for match in re.finditer(SCOPE, question, re.I):
        if not negated_prefix(question, match.start()):
            return match.group()
    return None


def normalized_quote(quote, question, history=()):
    quoted = " ".join(quote.split()).casefold()
    texts = [question] + [row.get("content", "") for row in history if row.get("role") == "user"]
    return bool(quoted) and any(quoted in " ".join(text.split()).casefold() for text in texts)


def affirmative_scope_quote(quote, question, history=()):
    if not quote.strip():
        return False
    quoted = " ".join(quote.split()).casefold()
    texts = [question] + [row.get("content", "") for row in history if row.get("role") == "user"]
    for raw in texts:
        text = " ".join(raw.split()).casefold()
        start = text.find(quoted)
        if start < 0:
            continue
        for marker in re.finditer(SCOPE, text, re.I):
            if start <= marker.start() < start + len(quoted) and not negated_prefix(text, marker.start()):
                return True
    return False


def update_request(question):
    return bool(re.search(r"what(?:'s| is| has)?\s+(?:changed|new)|anything new|tell me what is new|"
        r"(?:changes?|updates?|new information)\b.{0,55}\bsince\b|(?:changed|updated)\s+since|"
        r"was\b.{0,35}\b(?:neu|geändert)|neuigkeiten|änderungen\b.{0,50}\bseit\b", question, re.I))


def novelty_claim(text):
    return bool(re.search(r"\b(?:new|updated|revised|recent)\s+(?:guidance|recommendations?|clinical information|"
        r"safety information|label|communications|precautions|details)\b|"
        r"\b(?:changes?|changed|updates?|new)\b.{0,65}\bsince\b|"
        r"\b(?:neu|aktualisiert\w*|geändert\w*)\s+(?:empfehlungen|sicherheitshinweise|fachinformation|details)\b", text, re.I))


def scope_evidence(chunks):
    """Pass the actual eligible indication excerpt to intent classification, never workbook placeholders."""
    found = []
    for chunk in chunks:
        match = re.search(r"4\.1\s+Therapeutic indications\s+(.*?)(?=4\.2|$)", chunk["text"], re.S | re.I)
        if match:
            found.append({"id": chunk["id"], "text": match.group(1).strip(), "version_id": chunk["version_id"]})
    return found
