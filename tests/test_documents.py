import pymupdf as fitz

from camzyos.documents import extract, soft_chunks


def test_soft_limit_keeps_long_sentence_intact():
    sentence = "This is one deliberately long sentence " + "with words " * 30 + "ending here."
    result = soft_chunks([{"page": 3, "text": sentence, "requires_review": False}], target=80)
    assert len(result) == 1
    assert result[0]["text"] == sentence
    assert result[0]["page"] == 3


def test_review_page_excluded_and_provenance_preserved():
    pages = [{"page": 1, "text": "Allowed sentence. " * 10, "requires_review": False},
             {"page": 2, "text": "Unverified diagram decisions. " * 10, "requires_review": True},
             {"page": 3, "text": "Another allowed sentence. " * 10, "requires_review": False}]
    result = soft_chunks(pages, target=100)
    assert result
    assert all("Unverified" not in c["text"] for c in result)
    assert all(c["page"] in {1, 3} for c in result)
    assert all(c["page_end"] == c["page"] for c in result)


def test_repeated_margins_removed_but_body_qualifier_kept(tmp_path):
    path = tmp_path / "headers.pdf"
    doc = fitz.open()
    for i in range(4):
        page = doc.new_page()
        page.insert_text((40, 30), "Repeated publisher header")
        page.insert_text((40, 160), "Important clinical qualifier remains in the body.")
        page.insert_text((40, 810), str(i + 1))
    doc.save(path)
    doc.close()
    pages, audit = extract(path, {})
    assert all("Repeated publisher" not in p["text"] for p in pages)
    assert all("Important clinical qualifier" in p["text"] for p in pages)
    assert all(a["removed_margin_lines"] for a in audit)

