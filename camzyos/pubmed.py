"""PubMed discovery uses fixed topic queries: no HCP/patient text leaves in a search."""
import hashlib
import json
import os
import time
import xml.etree.ElementTree as ET

import httpx

TOPICS = {"initiation": "treatment initiation", "monitoring": "echocardiography monitoring",
          "safety": "safety adverse events", "efficacy": "clinical trial",
          "interactions": "drug interactions", "access": "health care",
          "general": "obstructive hypertrophic cardiomyopathy"}
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def discover(topic: str, limit=5):
    query = '(mavacamten[Title/Abstract] OR CAMZYOS[Title/Abstract]) AND ' + TOPICS.get(topic, TOPICS["general"])
    common = {"db": "pubmed", "tool": "camzyos_contextual_prototype"}
    if os.getenv("NCBI_API_KEY"):
        common["api_key"] = os.environ["NCBI_API_KEY"]
    if os.getenv("NCBI_EMAIL"):
        common["email"] = os.environ["NCBI_EMAIL"]
    with httpx.Client(timeout=25, follow_redirects=True) as client:
        response = client.get(BASE + "esearch.fcgi", params={**common, "term": query, "retmode": "json",
                                                            "retmax": min(limit, 10), "sort": "relevance"})
        response.raise_for_status()
        ids = response.json()["esearchresult"]["idlist"]
        if not ids:
            return []
        time.sleep(.35)
        response = client.get(BASE + "efetch.fcgi", params={**common, "id": ",".join(ids), "retmode": "xml"})
        response.raise_for_status()
    return parse_records(response.text)


def parse_records(xml):
    result = []
    for article in ET.fromstring(xml).findall(".//PubmedArticle"):
        def text(path, node=article):
            found = node.find(path)
            return "".join(found.itertext()) if found is not None else ""
        pmid = text(".//MedlineCitation/PMID")
        if not pmid.isdigit():
            continue
        flags = [e.get("RefType", "") for e in article.findall(".//CommentsCorrections")]
        types = ["".join(e.itertext()) for e in article.findall(".//PublicationType")]
        problematic = any(x in flags for x in ("RetractionIn", "RetractionOf", "ExpressionOfConcernIn",
                                               "ExpressionOfConcernFor", "ErratumIn", "ErratumFor")) or \
            any(t in types for t in ("Retracted Publication", "Retraction of Publication"))
        doi = next((e.text for e in article.findall(".//ArticleId") if e.get("IdType") == "doi"), None)
        abstract = "\n".join("".join(e.itertext()) for e in article.findall(".//Abstract/AbstractText"))
        authors = [" ".join(filter(None, [a.findtext("LastName"), a.findtext("Initials")]))
                   for a in article.findall(".//Author")]
        result.append({"id": f"PMID:{pmid}", "pmid": pmid, "title": text(".//ArticleTitle"), "authors": authors,
                       "journal": text(".//Journal/Title"), "year": text(".//PubDate/Year"), "doi": doi,
                       "text": abstract, "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                       "abstract_only": True, "publication_types": types, "flags": flags,
                       "requires_review": problematic or not abstract})
    return result


def eligible_records(records, approved_pmids):
    return [{"id": r["id"], "version_id": r["id"] + ":" + hashlib.sha256(
                json.dumps(r, sort_keys=True).encode()).hexdigest()[:12], "text": r["text"], "page": None,
             "page_end": None, "section": "Abstract only",
             "source": {"id": r["id"], "title": r["title"], "url": r["url"], "pmid": r["pmid"],
                        "doi": r["doi"], "journal": r["journal"], "year": r["year"], "authors": r["authors"],
                        "contribution": "Reviewed publication abstract; full text not accessed."}}
            for r in records if r["pmid"] in {str(x) for x in approved_pmids} and not r["requires_review"]]

