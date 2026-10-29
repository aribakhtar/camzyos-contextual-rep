# Initial build verification — 30 October 2026

## Completed and checked

- Python 3.13 environment installed; dependency consistency check passes. Graphiti 0.31.2, Neo4j GraphRAG 1.23.0 and RAGAS 0.4.3 are integrated. `requirements.lock` captures the tested environment. RAGAS needs the pinned `langchain-community==0.4.1`; 0.4.2 removed an import RAGAS still uses.
- **39 automated tests pass**, including identity/context isolation, consent, source eligibility, atomic replacement/withdrawal, citation IDs, chunk boundaries, handoff drafts, Graphiti scoping, embedding dimensions, RAGAS initialization and all four Streamlit views. Ruff passes. Local warnings were an upstream Graphiti/Pydantic deprecation and Windows temporary-directory cleanup warnings, not failing assertions.
- Actual workbook loaded: eight HCP profiles, eight personality records and 41 historical interactions. Its clinical placeholders are excluded from the clinical corpus.
- Eight source entries parsed/staged, including the additional German Fachinformation. Current local active evidence is **20 EMA SmPC prose passages**. The publisher download matches the supplied EU PDF by SHA-256. Hashes, statuses and excluded page lists are recorded in [the inventory](source-inventory.json).
- Portable Neo4j runs locally. The document vector index and Graphiti schema were initialized. An actual Neo4j write/retrieval test passed using deterministic mocked embedding responses; its synthetic test node was removed. This verifies the database integration, not semantic retrieval quality.
- Live PubMed ESearch/EFetch returned two verified PMID records. A correction flag on one record correctly marked it for review. Neither record was automatically approved for answers.
- Streamlit was started on localhost. UI behavior was exercised with Streamlit AppTest. The in-app browser connection was unavailable in this environment, so visual browser inspection is not claimed.
- Source update operations, source/context displays, optional PubMed, baseline comparisons and a RAGAS evaluation runner are implemented. The model-answer workflow is tested with controlled responses.

## Requires the user's key

Live generation, actual embeddings, Graphiti extraction/recall on seeded HCP memory, and scored baseline/contextual comparisons have **not** been run. The missing key is intentionally left for the user in ignored `.env`. Configure it, run document `sync` and Graphiti `seed`, then execute the evaluation cases. API availability, latency, cost and clinical answer quality still need to be measured.

No clinical quality score or improvement percentage has been invented. A model-based verification step can still miss an error; the finite tests do not establish a universal no-hallucination guarantee.

## Content and scope limits

1. Dosing/monitoring diagrams and table-heavy pages are excluded from plain-text retrieval. Questions requiring omitted algorithms should hand over. Their exclusion reduces coverage; it is not evidence that clinical guidance is absent.
2. The German Fachinformation remains staged. Its multi-column layout, line hyphenation and structured pages need a reviewed extraction before activation. The current answer corpus is the applicable EU English SmPC; generated language can follow the HCP's German preference.
3. Verified hospital/payer documents and explicit HCP-to-account affiliations were not provided. The architecture accepts scoped sources and `account_map`; it cannot supply real local rules from the workbook placeholders.
4. PubMed is off by default and the reviewed-PMID allowlist is empty. Discovery records appear in a review panel; full-text research ingestion is not implemented.
5. Email selection is a synthetic-demo login. Production authentication, reviewer roles and deployment hardening are not implemented. The reviewer source-management view is local and trusted.
6. Handoffs are downloadable drafts, with compact extractive context/conversation summaries. There is no external rep/MSL/PV/Quality connector or automatic sending. Proactive outreach is not implemented.
7. Already-received workbook content enters personalization. There is no automatic material-sending feature; the delivery-version store is ready for a future explicit delivery workflow. Legacy workbook material names do not establish exact delivered PDF versions.
8. Updates are checked on demand through the UI/CLI. There is no background folder watcher, automatic regulatory-change interpretation or scheduled notification service.
9. Graphiti is optional at runtime: failures produce a visible warning and fall back to the supplied profile/history. Source retrieval has a visible BM25 fallback. This preserves a usable demo without presenting a fallback as a successful graph/vector call.

See [the evaluation guide](evaluation.md) for what to measure next and [the complete product context](context.md) for the agreed scope.
