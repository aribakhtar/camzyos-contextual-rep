# Initial build verification — 30 October 2026

**Latest checks:** 73 automated tests pass. Separate preparation, strict index readiness, replacement indexing/activation and the Streamlit Evaluation view have been exercised. Live RAGAS results and remaining quality gaps are recorded at the end of this document; earlier sections retain the build history.

## Completed and checked

- Python 3.13 environment installed; dependency consistency check passes. Graphiti 0.31.2, Neo4j GraphRAG 1.23.0 and RAGAS 0.4.3 are integrated. `requirements.lock` captures the tested environment. RAGAS needs the pinned `langchain-community==0.4.1`; 0.4.2 removed an import RAGAS still uses.
- **39 automated tests pass**, including identity/context isolation, consent, source eligibility, atomic replacement/withdrawal, citation IDs, chunk boundaries, handoff drafts, Graphiti scoping, embedding dimensions, RAGAS initialization and all four Streamlit views. Ruff passes. Local warnings were an upstream Graphiti/Pydantic deprecation and Windows temporary-directory cleanup warnings, not failing assertions.
- Actual workbook loaded: eight HCP profiles, eight personality records and 41 historical interactions. Its clinical placeholders are excluded from the clinical corpus.
- Eight source entries parsed/staged, including the additional German Fachinformation. Current local active evidence is **20 EMA SmPC prose passages**. The publisher download matches the supplied EU PDF by SHA-256. Hashes, statuses and excluded page lists are recorded in [the inventory](source-inventory.json).
- Portable Neo4j runs locally. The document vector index and Graphiti schema were initialized. An actual Neo4j write/retrieval test passed using deterministic mocked embedding responses; its synthetic test node was removed. This verifies the database integration, not semantic retrieval quality.
- Live PubMed ESearch/EFetch returned two verified PMID records. A correction flag on one record correctly marked it for review. Neither record was automatically approved for answers.
- Streamlit was started on localhost. UI behavior was exercised with Streamlit AppTest. The in-app browser connection was unavailable in this environment, so visual browser inspection is not claimed.
- Source update operations, source/context displays, optional PubMed, baseline comparisons and a RAGAS evaluation runner are implemented. The model-answer workflow is tested with controlled responses.

## Live validation still pending

Live generation and actual embeddings have now been exercised for the indication regression below. Graphiti extraction/recall on seeded HCP memory and scored baseline/contextual comparisons have **not** been validated. The remaining live steps include Graphiti `seed` and the broader evaluation cases. API reliability, latency, cost and clinical answer quality across the use cases still need to be measured.

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
9. Graphiti is optional at runtime: failures produce a visible warning and fall back to the supplied profile/history. Document retrieval now requires a complete vector index and successful vector search. BM25 supplements vector search; it cannot replace an unavailable index.

See [the evaluation guide](evaluation.md) for what to measure next and [the complete product context](context.md) for the agreed scope.

## Portability update

The supplied workbook and all seven supplied PDFs are now committed in `assets/`, alongside the added German Fachinformation. Checksums confirm the original bytes are preserved. Defaults use paths relative to the repository root; the existing local `.env` now points to those assets and its credentials were preserved.

`python -m camzyos.cli prepare` reconstructs generated state from the bundled inputs and restores only the exact reviewed EMA prototype version. A separate checkout exported from Git's index, with no `.env` and no original-machine path overrides, successfully loaded eight HCPs/41 interactions and rebuilt 20 active passages. Four new portability tests bring the local suite to **43 passing tests**, including changed-file review rejection and withdrawal preservation.

The README now includes clone/install/prepare/sync/seed/run commands for Windows and macOS/Linux. `compose.yaml` provides an optional Neo4j container; its official amd64/arm64 image tag was verified, while local execution continues to use the already-running portable Windows Neo4j. CI validates Compose configuration syntax.

The user has now supplied an API key locally. These portability checks do not constitute a live clinical quality benchmark or a completed Graphiti seed.

## Approved-indication regression — 30 October 2026

The question "What is CAMZYOS approved for in Germany?" reproduced a false insufficient-evidence handoff. Retrieval found the indication passage and the model generated a supported clinical statement, but placed a document ID in `context_used`. The deterministic context check rejected it; the old message incorrectly described this as missing evidence.

- Answer schemas now enumerate the actual retrieved passage IDs and the current HCP context keys separately. Unknown HCPs can return only an empty personal-context list. Existing eligibility and ID validation remain enforced.
- A live UI test also exposed a correct statement attached to the wrong passage. Verification now receives only the evidence cited by each claim and the selected personal context. One correction attempt is reverified before display; repeated validation failure produces a validation-specific handoff, without exposing the rejected draft.
- The empty document vector index was populated with real embeddings for all **20 active passages**. This first fix made BM25 fallback explicit; the subsequent preparation change below removes that fallback and requires a complete vector index.
- Live Streamlit AppTest runs returned the approved indication with the correct source passage for Anna, an unknown email, and a German question from another HCP. The unknown session had no personal context. A deliberately incorrect indication citation failed live verification; a patient-specific request still produced a handoff. These checks did not save conversations.
- **54 automated tests pass**, with Ruff clean. New regressions cover separate identifier schemas, unknown-user context, per-claim verification inputs, bounded correction, accurate refusal reasons and empty-vector reporting. The evaluation runner now includes the approved-indication question.

These focused checks establish the reported question's retrieval/citation path, not a full clinical benchmark or a guarantee of error-free personalization. Human review of contextual phrasing, language adherence and completeness is still required. The structured-output implementation follows [official OpenAI documentation](https://developers.openai.com/api/docs/guides/structured-outputs); schema validity alone does not establish factual correctness.

## Separate preparation and evaluation — 30 October 2026

The document lifecycle is now explicit: `build` prepares the bundled corpus before chat; a replacement upload or `ingest` parses, chunks and indexes a staged version. Reviewed activation checks that version's complete index before switching the active pointer. A failed replacement leaves the old active version intact. Chat verifies the active passages, embedding model/dimensions, stored text and ONLINE index state; an incomplete/unavailable index produces a setup error without a lexical-only clinical answer.

Streamlit now has an **Evaluation** view backed by `camzyos/evaluation.py` and `evals/retrieval.py`. Four source-pinned cases test retrieval hit/recall and rank, with real RAGAS context precision/recall and optional answer faithfulness. References are exact source-checked excerpts; independent clinical review is pending. Source changes invalidate references. Reports preserve outputs, actual retrieval queries, source IDs, scores, errors and any available judge details.

An initial live contextual indication case scored reference hit/recall 1.0, reciprocal rank 1.0, RAGAS context precision approximately 1.0, context recall 1.0, and faithfulness **0.67**. Four raw-question retrieval tests all found their annotated passage in the top six, with reciprocal ranks **0.25, 0.50, 0.17, 1.00** and RAGAS context precision **0.25, 0.71, 0.27, 1.00** (indication, ingredient, administration, storage). Context recall was 1.0 for all four. These are small-sample observations, not quality guarantees. They expose ranking weaknesses and a need to inspect the faithfulness shortfall. The first run's installed RAGAS metrics returned numeric scores without explanatory traces, so the exact reason for the shortfall has not been established.

LangGraph is not an application orchestrator here. The researched Graphiti example uses it; this repository directly uses Graphiti's memory library and a bounded Python workflow. The installed LangGraph dependency comes through the evaluation stack. Document indexing, graph memory and evaluation are separate responsibilities.

An isolated live replacement test parsed and embedded 20 new-version passages, verified the old version remained active before publication, then activated the fully indexed replacement. Its test vectors were removed afterward; the application's active corpus and vectors remained unchanged. Streamlit AppTest exercised actual RAGAS answer scoring and the missing-index setup block. The live UI answer check also returned faithfulness 0.67. The suite now has **73 passing tests**; Ruff passes. Graphiti transports now close before their event loop ends, fixing an observed cleanup warning during sequential memory/evaluation calls.
