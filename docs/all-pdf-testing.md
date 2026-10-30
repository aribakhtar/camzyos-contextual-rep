# Test retrieval across every bundled PDF

Every supplied PDF is now parsed, chunked, embedded and searchable for extraction/retrieval testing. Indexing a file for testing does not activate it as German clinical evidence. The two paths use separate Neo4j labels, indexes and passage IDs; inspection text cannot enter the clinical answer schema or verifier.

| PDF | Pages | Inspection chunks |
|---|---:|---:|
| EMA EU product information | 52 | 93 |
| German Fachinformation | 12 | 54 |
| EU risk-management plan | 84 | 159 |
| EMA public overview | 3 | 6 |
| EMA procedure history | 3 | 4 |
| EMA archived procedure history | 6 | 8 |
| US FDA label (`214998s010lbl.pdf`) | 31 | 57 |
| US BMS prescribing information (`pi_camzyos.pdf`) | 12 | 51 |
| **Total** | **203** | **432** |

These counts describe the bundled snapshot inspected on 30 October 2026, not hardcoded acceptance thresholds. Every page has extractable text. Each inspection passage retains its exact page-text offsets; preparation verifies that the chunks cover all non-whitespace text on every page. Short pages and pages with tables/diagrams are retained, with review flags. Their reading order, table semantics and diagram branches are not clinically validated by embedding them. No OCR or synthetic clinical reconstruction is used.

## Code locations

| Stage | Clinical-answer corpus | All-PDF inspection corpus |
|---|---|---|
| Parse | `documents.extract()` in [documents.py](../camzyos/documents.py) | `prepare_source()` in [inspection.py](../camzyos/inspection.py): raw PyMuPDF text plus the cleanup/layout audit |
| Chunk | `documents.soft_chunks()`: sentence-preserving chunks, excluding review pages | `inspection._page_chunks()`: sentence-preserving chunks within each page, retaining review pages and short text |
| Embed/index | `graph.index_chunks()` in [graph.py](../camzyos/graph.py) | `inspection.index_chunks()`: batches of up to 32 texts; compatible completed embeddings are reused |
| Search | [retrieval.py](../camzyos/retrieval.py): eligible vector + BM25 fusion | `inspection.search()`: separate vector + BM25 fusion, source/account filters, no generated answer |
| Orchestrate | [ingest.py](../camzyos/ingest.py) | `inspection.build()`; `index-all` command |

Both paths use the configured embedding model and dimensions. The current configuration is `text-embedding-3-small`, 1,536 dimensions. Array inputs and dimensions follow the [OpenAI embeddings API](https://developers.openai.com/api/reference/python/resources/embeddings/methods/create), checked against the installed SDK using OpenAI Docs.

## Build and verify

From the repository directory in PowerShell, with Neo4j running and the API key saved locally:

```powershell
# Clinical eligibility/review rules still govern this corpus.
.\.venv\Scripts\python.exe -m camzyos.cli build

# All configured PDFs, including excluded and staged sources.
.\.venv\Scripts\python.exe -m camzyos.cli index-all

# Fail unless BOTH indexes are current, complete and online.
.\.venv\Scripts\python.exe -m camzyos.cli doctor --strict --all-documents
```

`scripts/start.ps1` now runs clinical build, all-PDF indexing, the combined strict check and HCP seeding before starting Streamlit. `-PrepareOnly` performs those steps without launching another UI. Plain `doctor --strict` continues to check clinical chat readiness; add `--all-documents` for full-corpus testing.

The expected current readiness is:

- Clinical index `camzyos_embeddings`: 20 eligible SmPC passages.
- Inspection index `camzyos_inspection_embeddings`: 432 passages from all eight PDFs.

The inspection manifest under `data/inspection/manifest.json` contains versioned source metadata, exact text, page audits, source hashes and passage IDs. Immutable per-document artifacts are in `data/inspection/versions/`; source snapshots remain under `data/snapshots/`. Changed PDF bytes, source metadata or chunk settings invalidate inspection readiness until rebuilt. Missing vectors, incompatible dimensions/index schema, partial builds and failed verification are reported as failures. Inspection commands do not register or activate clinical sources.

## Search all PDFs

In the running app, open **Sources & updates → All-PDF testing index**. Check the per-source counts, select a PDF or all PDFs, enter a query, and click **Search all-PDF testing index**. Results show source, PDF page, inspection ID, raw extracted text and layout-review flags; a JSON download retains the result. Searches make query-embedding API calls.

Equivalent CLI examples:

```powershell
.\.venv\Scripts\python.exe -m camzyos.cli inspect --source us_fda --query "REMS"
.\.venv\Scripts\python.exe -m camzyos.cli inspect --source eu_changes --query "variation"
.\.venv\Scripts\python.exe -m camzyos.cli inspect --query "risk management"
```

The clinical answer path never reads this index. Source-specific inspection can therefore exercise a US document without making it evidence for German answers. `clinical_evidence` is always false for inspection passages, including passages from the active EMA PDF. Account-owned sources are filtered to the selected HCP's explicit account mapping; CLI inspection defaults to public/general scope. The app remains a local synthetic-profile prototype, without production authentication/reviewer roles.

## Run the corpus smoke test

```powershell
.\.venv\Scripts\python.exe -m evals.corpus
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

`evals.corpus` performs a live source-scoped lookup from each of the eight PDFs and checks clinical retrieval remains within its eligible IDs. It records the pinned source/passages, actual results, reference ranks and errors in a timestamped JSONL report. It makes embedding calls, not answer-generation or RAGAS judge calls. It pins source snapshots across the run and retains each failure.

The first completed live run found each sampled passage at rank 1 in its own source and passed clinical-isolation checks for all eight PDFs. This is an exact-passage infrastructure smoke test, not a clinical correctness or unseen-question benchmark. The 20 clinical passages were compared before and after indexing and remained identical.

For clinical RAGAS evaluation, continue using independently reviewed references from the eligible clinical corpus. Inspection IDs deliberately fail clinical reference validation. For coverage and exclusion tests, use inspection passages and explicit expected source/decision labels; do not turn unreviewed extracted text into gold clinical answers. See [the testing workflow](testing-workflow.md) and [adversarial test design](adversarial-test-data.md).
