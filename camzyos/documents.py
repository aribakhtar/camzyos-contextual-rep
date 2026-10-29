"""PyMuPDF extraction, repeated-margin cleanup and sentence-preserving soft chunks."""
import hashlib
import re
from bisect import bisect_right
from collections import Counter

import pymupdf as fitz
import pysbd

SECTION = re.compile(r"(?m)^\s*(\d{1,2}(?:\.\d{1,2})?)\.?\s+([A-ZÄÖÜ][^\n]{3,100})$")


def margin_key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\b\d+\b", "#", text)).strip().casefold()


def extract(path, source: dict) -> tuple[list[dict], list[dict]]:
    """Remove only repeated marginal text/page numbers, never all headings or footnotes."""
    pages, audit = [], []
    with fitz.open(path) as doc:
        raw, counts = [], Counter()
        for page in doc:
            lines = []
            for block in page.get_text("dict", flags=fitz.TEXT_DEHYPHENATE)["blocks"]:
                for line in block.get("lines", []):
                    text = "".join(s["text"] for s in line["spans"]).strip()
                    if text:
                        y0, y1 = line["bbox"][1], line["bbox"][3]
                        margin = y1 < page.rect.height * .07 or y0 > page.rect.height * .94
                        lines.append((text, margin))
            counts.update({margin_key(t) for t, marginal in lines if marginal})
            raw.append(lines)
        repeated = {s for s, n in counts.items() if n >= max(3, len(doc) * .5)}
        start, end = source.get("pages", [1, len(doc)])
        for number, (page, lines) in enumerate(zip(doc, raw), 1):
            removed = [t for t, m in lines if m and (margin_key(t) in repeated or t.isdigit())]
            kept = [t for t, m in lines if not (m and (margin_key(t) in repeated or t.isdigit()))]
            # Diagrams and tables are not flattened into reliable clinical instructions.
            structured = number in source.get("review_pages", []) or len(page.get_drawings()) > 25
            text = "\n".join(kept).replace("\u00ad", "")
            audit.append({"page": number, "removed_margin_lines": removed,
                          "requires_review": structured, "text_chars": len(text)})
            if start <= number <= end:
                pages.append({"page": number, "text": text, "requires_review": structured})
    return pages, audit


def soft_chunks(pages: list[dict], target=1600, overlap=1, language="en") -> list[dict]:
    """Sentence size is a soft limit: an oversized sentence is kept intact.

    Sentences may span adjacent pages; each chunk retains its full page range.
    A page flagged for review breaks the run and never enters answer retrieval.
    """
    segmenter = pysbd.Segmenter(language=language if language in {"en", "de"} else "en",
                               clean=False, char_span=True)
    runs, current = [], []
    for page in pages:
        if page["requires_review"] or len(page["text"].strip()) < 100:
            if current:
                runs.append(current)
                current = []
        else:
            current.append(page)
    if current:
        runs.append(current)
    chunks = []
    for run in runs:
        starts, text = [], ""
        for page in run:
            starts.append(len(text))
            text += page["text"] + "\n\n"
        headings = [(m.start(), m.group(0).strip()) for m in SECTION.finditer(text)]
        sentences = segmenter.segment(text)
        group, size = [], 0

        def emit(items):
            if not items:
                return
            first, last = items[0].start, items[-1].end
            section = next((name for pos, name in reversed(headings) if pos <= first), "Product information")
            body = text[first:last].strip()
            if body:
                chunks.append({"text": body, "page": run[bisect_right(starts, first)-1]["page"],
                               "page_end": run[bisect_right(starts, max(first, last-1))-1]["page"],
                               "section": section})

        for sentence in sentences:
            if group and size + len(sentence.sent) > target:
                emit(group)
                group = group[-overlap:] if overlap and len(group) > overlap else []
                size = sum(len(s.sent) for s in group)
            group.append(sentence)
            size += len(sentence.sent)
        emit(group)
    return chunks


def digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

