# CAMZYOS document review and retrieval recommendation

> Design/research record. See [implementation status](status.md) for what is now built, tested and still limited.

Reviewed 30 October 2026. Source folder: the supplied local `product information 1` folder (`PDF_DIR` in .env).

**Finding:** The folder contains seven PDFs, totalling 191 PDF pages. They include EU professional information, patient-facing information, regulatory history, a risk-management plan and two US prescribing-information documents. They should not become one unfiltered retrieval collection.

All seven PDFs have extractable text. Extraction does not establish correct reading order, completeness, clinical accuracy or current-version status. This was a document inventory and retrieval-design review, not clinical validation. Original files were not modified.

**How the supplied documents should be used**

| Supplied file | PDF pages | Observed identity/content | Proposed retrieval role |
|---|---:|---|---|
| `camzyos-epar-product-information_en.pdf` | 52 | EU product information. Annex I/SmPC: pages 1–24; Annex II: 25–29; Annex III: 30–52, including labelling and a patient leaflet starting at page 45. | Primary candidate for EU professional product evidence after current-version and source-policy checks. Classify sections separately instead of marking every page HCP content. |
| `camzyos-epar-risk-management-plan_en.pdf` | 84 | EU RMP version 6.1. Cover records data-lock point 27 October 2024 and final sign-off 29 September 2025. | Supporting risk-management and evidence-limitation context after review. It does not independently authorize indications or replace the current SmPC. |
| `camzyos-epar-medicine-overview_en.pdf` | 3 | Public EMA overview; says last updated June 2023. | Public background, labelled by audience and age. Not the default source for detailed HCP instructions. |
| `camzyos-epar-procedural-steps-taken-scientific-information-after-authorisation_en.pdf` | 3 | Regulatory procedure log; visible entry dated 30 May 2025, with other 2025 entries. | Historical change-discovery context. Procedure dates and descriptions must be reconciled with the applicable product-information version. |
| `camzyos-epar-procedural-steps-taken-scientific-information-after-authorisation-archive_en.pdf` | 6 | Archived regulatory procedure history, including a December 2024 entry. | Historical context only; preserve historical status explicitly. |
| `214998s010lbl.pdf` | 31 | FDA US label, with April 2025 revision markings and US REMS references. | Exclude from the default German-market answer corpus. Retain as an excluded source and as a negative retrieval test. |
| `pi_camzyos.pdf` | 12 | BMS US prescribing information, also with April 2025 revision markings and US REMS references. | Exclude from the default German-market answer corpus. Do not treat filename `pi` as evidence that it is German product information. |

The two US documents are distinct files by SHA-256. This review did not establish their complete semantic equivalence. The implementation records hashes, page counts and extraction diagnostics in its local source registry. See [current implementation status](status.md).

The folder has no identified German-language Fachinformation. English-language EU product information can still be relevant to Germany: language and jurisdiction must be represented separately. Public accessibility and regulatory provenance also do not automatically imply company approval for every use in this chatbot.

**Graphiti's example and the missing document pipeline**

The inspected Graphiti sales example ingests structured product JSON as episodes, extracts graph facts and searches those facts during conversation. That is retrieval-augmented generation in a broad sense. It is not a ready PDF ingestion pipeline with section-aware chunks, preserved tables, page citations, source approval, jurisdiction filtering and version control. [Official example](https://help.getzep.com/graphiti/integrations/lang-graph-agent), [source notebook](https://github.com/getzep/graphiti/blob/main/examples/langgraph-agent/agent.ipynb).

Recommended division of responsibility:

1. **Personal context:** Directly import the supplied profile fields and relationships; use Graphiti for relevant interaction memory and temporal context. Scope every request to the application-resolved user.
2. **Product evidence:** Extract and preserve document passages, section identifiers, original PDF page numbers, tables/figures and source metadata. Retrieve eligible passages separately from personal memory.
3. **Answer construction:** Use personal context to select emphasis, depth and already-covered topics. Support product claims with document evidence, attaching citations to the passages actually used. If evidence is missing or a handoff rule applies, abstain or route accordingly.

Both stores can use Neo4j with distinct labels/indexes and explicit application boundaries. A second vector database is not required. Neo4j's official Python GraphRAG library offers retrieval components and a PDF/knowledge-graph construction pipeline; the latter is explicitly marked experimental. We can use selected components without extracting every clinical statement into an LLM-generated graph. [RAG guide](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html), [KG construction guide](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html).

Implementation caveat: the current RAG guide says its general `filters` interface is not supported by the Hybrid retrievers. Therefore, do not assume attaching a `market=DE` filter to a stock HybridRetriever is sufficient. For this small corpus, begin with eligible-source indexes and a filtered vector retriever; add lexical retrieval with explicit scope enforcement when needed. Keep all disallowed passages out of generation context.

**Extraction issue that affects answer quality**

The EU product-information PDF contains treatment flowcharts on pages 4–6 and a table on page 7. Page 5 was rendered and visually inspected: its arrows, branches and footnotes carry meaning that a linear text dump does not reliably preserve. Text extraction of the US labels also interleaves columns. Therefore:

- Split by section and document structure, not a fixed number of characters alone.
- Keep tables with column headings, footnotes and associated text.
- Preserve figure/page images and verify any structured transcription of decision diagrams before enabling detailed answers from them.
- Keep extracted material separate from model-written summaries; summaries must retain supporting page references and review status.
- Store both PDF page number and printed page label when they differ.

Sparse-text pages observed in the EU information PDF are section-title pages; the sparse last pages of procedure logs are not by themselves evidence that OCR is needed. Avoid an unconditional OCR pass merely because a page contains little text.

**Source and provenance records**

Every supplied or added source should have: stable source ID; supplied/public origin; original path or URL; publisher; product; jurisdiction; language; document type; audience by section; version/effective dates when verified; retrieval timestamp; hash; review/eligibility status; supersession relationship; and a short statement of what it contributes. Every chunk should point back to its source, section and page. Unknown dates stay unknown; filesystem modification times and PDF creation dates are not clinical effective dates.

Workbook placeholder clinical text must remain explicitly synthetic and excluded from factual retrieval. The workbook can supply profile/history context, routing rules and content identifiers. Real documents receive their own provenance and version records; they must not silently inherit the placeholder records' approval or expiry dates.

Public information should be acquired through an allowlisted, logged process, preferably during ingestion for this prototype. Newly discovered material should be classified and reviewed before entering the eligible answer corpus. Unknown-email users still use the appropriate approved/general-content mode specified in the requirements.

**Additional external sources consulted in this review**

| Source | What it contributed | Status |
|---|---|---|
| [BMS German CAMZYOS Fachinformation](https://fi.b-ms.de/camzyos) | Identified an additional German-language professional product-information source. The retrieved PDF has 12 pages and is labelled May 2025. | Candidate clinical source; inspected through web retrieval. Not imported into a chatbot or assigned internal approval. A complete latest-version comparison was not performed. |
| [EMA CAMZYOS EPAR page](https://www.ema.europa.eu/en/medicines/human/EPAR/camzyos) | Official product landing page for provenance and document discovery. Fetched page states it was last updated 23 October 2025. | Reference/discovery source; does not prove that supplied PDF bytes equal the currently published files. |
| [Graphiti LangGraph example](https://help.getzep.com/graphiti/integrations/lang-graph-agent) and [notebook](https://github.com/getzep/graphiti/blob/main/examples/langgraph-agent/agent.ipynb) | Established the example's product-JSON ingestion and graph-retrieval behavior, and the gap relative to document RAG. | Technical reference only. |
| [Neo4j RAG guide](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html) | Verified retrieval options, provenance formatting and the hybrid-retriever filtering limitation. | Technical reference only. |
| [Neo4j KG construction guide](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html) | Verified PDF-loading/chunking components and the experimental status of the construction pipeline. | Technical reference only. |

**Verification performed:** extracted all seven PDFs locally with PyMuPDF, calculated file hashes, inspected document identities and section boundaries, rendered one clinically structured page, inspected the previously downloaded Graphiti notebook and fetched current official documentation. No application or clinical-answer pipeline was built or evaluated in this review.

**Search summary:** Used `webcmd web fetch` for the two Neo4j guides and the EMA landing page; used the web PDF reader for the German BMS Fachinformation. No browser fallback. An additional EMA fetch through the web reader returned HTTP 429; the prior successful webcmd fetch was retained and no retry loop was used. No missing source was replaced with placeholder clinical claims.
