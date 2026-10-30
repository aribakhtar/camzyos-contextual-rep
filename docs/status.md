# Initial build verification — 30 October 2026

**Subsequent routing/evidence fixes:** 343 automated tests and 14 subtests pass. Fifteen targeted live
case checks and four claim-audit checks met their expectations; inputs and HCP memory stayed unchanged.
The original `ray_001` contradiction is rejected by the new audit, all six missed symptom reports reach
PV drafts, and historical changes require reviewed comparison evidence. The initiation checklist still
produces a verification handoff; it no longer falsely claims the question is off-label. These are known
regressions, not a fresh 132-case/RAGAS benchmark. See [changes, query-planning flow and limits](guardrail-fixes.md)
and local `reports/guardrail-fixes-20261030T113049Z/`. The original scores below remain unchanged.

**Full rerun completed:** 310 automated tests and 14 subtests pass. The 132-case HCP set produced
36 answers and 96 handoffs with no application execution errors; clinical faithfulness averaged 0.911
over 36 answers. Four source-pinned questions repeated three times scored retrieval precision/recall
0.964/1.000 and contextual-answer precision/recall/faithfulness 0.897/1.000/0.903. All eight PDF inspection
checks passed. Inputs and HCP memory remained unchanged. These means are not clinical approval: review
found a cited-source contradiction despite faithfulness 1.0, wrong AE routes and unsupported temporal
updates. The new subjective contextualization rubric failed calibration spot-checks. Separate text/trace
checks found 14/132 outputs matching the recorded German-language target, own-HCP context declared by
36/36 answers, and retained history plus appropriate patient handoffs in both actual multi-turn cases.
See local `reports/full-evaluation-20261030T105623Z/review.html` and its `findings.md` for outputs,
denominators, initial scorer failures, deterministic recovery and limitations. The original golden
report is preserved. [Contextualization methodology](contextualization-evaluation.md) and
[current versus proposed flow](current-vs-proposed-flow.md) explain what was measured.

**Earlier feature checks:** 294 automated tests and 14 subtests passed on Windows; Ruff and dependency checks passed.
Full dated transcripts are retained, with automatic working-context summaries and explicit clear/forget
controls. Clinical retrieval now reranks up to 20 eligible candidates before returning six passages.
Both document indexes remain complete and ONLINE: 20 eligible clinical passages and 432 inspection
passages across eight PDFs/203 pages. The running app's Chat, Evaluation, and Sources & updates views,
HCP switching, transcript download, and explicit clearing passed actual browser checks.

A live 100-message test summarized 94 older messages into 150 tokens while retaining all original
messages. Its patient-specific follow-up produced a patient handoff; an unrelated general indication
question received an answer using the cached summary. The four paired retrieval smoke cases improved
reference ranks from 4/2/6/1 to 1/1/1/1; RAGAS context recall stayed at 1.0. These are known development
cases, not an independent clinical benchmark or a rerun of the 132-case HCP suite. Initial invalid-ID
failures were preserved and schema constraints tightened. Review also found summary attribution
errors: explicit subjects improved preference attribution, but some unsupported detail remains.
Summaries are lossy context and never clinical evidence. See [implementation and limits](conversation-and-reranking.md)
and local `reports/conversation-reranking-verification.md`. Historical checks and earlier clinical
limitations below remain relevant; no general clinical-quality improvement is claimed.

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

## Fresh Windows setup and seeded memory — 30 October 2026

Installed the locked development/evaluation environment under Python 3.13.7 on Windows 11. Created the missing ignored `.env`, generated a local database password, and used the API key entered locally by the user. The documented portable helper installed Java 21 and Neo4j 2026.10.1 without a Windows service or global Java changes.

Offline preparation loaded eight HCPs, eight personality records and 41 historical interactions from the bundled workbook and processed all eight PDFs. `build` created real embeddings for **20/20** eligible passages. `doctor` reports all input/key/connection flags true and the complete vector index **ONLINE**. Only the recorded EMA version is active; the other versions remain staged. No placeholder clinical text was indexed as evidence.

The first live `seed` failed with `NodeNotFoundError`: Graphiti 0.31.2 interprets `add_episode(uuid=...)` as reprocessing an existing episode. The integration now lets Graphiti assign a new UUID and checks a deterministic episode name inside the HCP's group to reuse an unchanged seed. Existing legacy UUIDs remain recognized. All **eight seeds** then completed, and a second invocation skipped all eight without repeating extraction. Live recall returned own-group facts for two HCPs, and a graph query found **zero cross-group relationships**. These checks establish import/scoping behavior, not the accuracy of every model-extracted fact.

Added a portable `stop` action with process identity checks, an isolated hidden console, and a PowerShell wrapper that restores inherited Ctrl-C handling before Java starts. The first stop attempt exposed Windows virtual-environment console behavior; this was corrected and a fresh start/stop/restart cycle passed. The original ignored-signal JVM was recovered once through its normal shutdown hooks using a local JDK attach helper, without force-killing it. All 20 vectors and eight seed episodes survived restart. Streamlit was also restarted through `scripts/start.ps1`.

**92 tests and 14 subtests pass**, with Ruff and `pip check` clean. The one pytest warning is an upstream Graphiti/Pydantic deprecation. Headless Chrome checked the fully rendered Chat, Compare, Evaluation, Sources & updates, and Context views, including the evaluation controls and source-index readiness. Conversation storage stayed off; the selected HCP's persisted chat history remained empty.

Live retrieval RAGAS results (six passages per query):

| Case | Expected passage rank | Reference hit/recall | Context precision | Context recall |
|---|---:|---:|---:|---:|
| Indication | 4 | 1.00 / 1.00 | 0.25 | 1.00 |
| Ingredient | 2 | 1.00 / 1.00 | 0.71 | 1.00 |
| Administration | 6 | 1.00 / 1.00 | 0.27 | 1.00 |
| Storage | 1 | 1.00 / 1.00 | 1.00 | 1.00 |

The contextual indication CLI evaluation returned the approved adult symptomatic NYHA II–III oHCM indication with citation `eu_smpc:9132b2e8e8aaa163:c72eb750:1` (PDF pages 2–3, indication on page 3). Its rewritten query ranked that passage fourth; context precision was 0.25, recall 1.00 and faithfulness **0.67**, with no metric execution errors. The installed judge returned no explanation/traces for the faithfulness shortfall. The generated introduction also exposed internal HCP context keys, a presentation defect that remains unresolved.

Separately, the same indication question in the actual Chat UI produced a **validation handoff** after the bounded correction attempt. It displayed no clinical claim or citation. This outcome is retained alongside the successful CLI answer; no reliable answer rate or quality improvement is claimed. Existing clinical verification, consent, source eligibility and HCP isolation checks were preserved. The same-model comparison benchmark and independent clinical review were not run during this setup.

Machine-local artifacts are ignored under `reports/`: `setup-summary.md`, `retrieval-ragas.jsonl`, `contextual-ragas.jsonl`, `browser-check.json`, `browser-pages-after-restart.json`, `memory-check.json`, screenshots, and test/build logs. These reports contain actual outputs and ranked evidence, never credentials. Their presence is specific to the machine that ran this setup.

## Preparation-first testing workflow — 30 October 2026

Fetched `origin` and created local branch `feature/rag-readiness-evaluation` from the current `main`, preserving the setup fixes. The user requested the application remain stopped while preparing a broader evaluation workflow.

- `scripts/start.ps1` now runs `scripts/prepare.ps1` before Streamlit: wait for the configured database, build/index eligible PDFs, require `doctor --strict`, and seed/reuse HCP memory. `-PrepareOnly` performs this pipeline without starting the UI. Failure at any stage blocks startup.
- Chat input is disabled before a question can be submitted when the eligible index or API key is missing. Backend readiness checks remain in place for changes after page load.
- The evaluation CLI accepts `--cases-file PATH` and `--repeats N`. Reports retain every repetition and the exact case-file SHA-256. Answerable-case handoffs, per-case exceptions, stale references and missing requested metrics are explicit failures. Low completed scores remain findings rather than execution errors.
- [The testing workflow](testing-workflow.md) explains startup, all UI views, development/validation/held-out question families, source-pinned references, repeated measurements, and separate handoff/isolation tests. Independent held-out annotations still need to be authored and reviewed; they were not fabricated from the four existing cases.

Verification: the database-off preparation check failed before indexing/UI startup as intended. A live preparation-only run verified **20/20 ONLINE** and reused all eight seeds while keeping port 8501 closed. Neo4j was then stopped; ports 7474, 7687 and 8501 were confirmed closed. **163 tests and 14 subtests pass**, with Ruff clean and one upstream Graphiti/Pydantic deprecation warning. A test clock mock was scoped to the helper so it no longer interferes with background library threads. No new live quality evaluations or retrieval/prompt tuning were performed in this workflow change.
