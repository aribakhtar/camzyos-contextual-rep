# CAMZYOS Contextual Rep

A Streamlit prototype for personalized CAMZYOS information for HCPs in Germany. It combines the supplied HCP workbook, Graphiti memory, and separately controlled document retrieval. Every generated clinical claim must reference retrieved evidence; unsupported requests produce a handoff draft.

**Current state:** runnable locally, with deterministic tests and live source checks. Add your API key for generation, embeddings, Graphiti extraction and RAGAS scoring. No live answer-quality improvement is claimed yet. See [verification and limitations](docs/status.md).

## Clone and run

**The inputs are included in Git:** [assets/hcp_context.xlsx](assets/hcp_context.xlsx) is the original workbook, and [assets/product_information](assets/product_information) contains all seven supplied PDFs plus the downloaded German Fachinformation. You do not need the original Desktop/Downloads folders. See [asset provenance and workbook usage](assets/README.md).

Install **Git** and **Python 3.13**. For the Docker database option, also install and start **Docker Desktop** on Windows/macOS, or Docker Engine with Compose on Linux. Windows users can instead use the included database helper below. No Neo4j cloud account or knowledge of graph queries is needed. This repo is private, so collaborators need GitHub access before cloning:

```shell
git clone https://github.com/aribakhtar/camzyos-contextual-rep.git
cd camzyos-contextual-rep
```

On Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -c requirements.lock -e '.[dev,eval]'
Copy-Item .env.example .env
```

On macOS/Linux:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements.lock -e '.[dev,eval]'
cp .env.example .env
```

Create `.env` only on a fresh clone; preserve an existing file containing your key. Set `OPENAI_API_KEY` and a `NEO4J_PASSWORD` of at least eight characters. Input paths already default to the committed assets in `config.yaml`; optional `.env` overrides can be relative to the repository root or absolute.

| Setting | What to enter |
|---|---|
| `OPENAI_API_KEY` | Your model API key; generation, embeddings, memory extraction and evaluation use it. |
| `NEO4J_PASSWORD` | A password you choose for your local database before its first setup. It is not an API key. |
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_DATABASE` | Leave the supplied defaults for the local database. |
| `NCBI_API_KEY` | Optional key for higher PubMed API request limits. Leave blank for this prototype. |
| `NCBI_EMAIL` | Optional developer contact email included in PubMed requests to NCBI; not an HCP email or email account password. |
| `WORKBOOK_PATH`, `PDF_DIR` | Leave blank to use the workbook and PDFs already in `assets/`. |

PubMed search is **off by default** (`pubmed_enabled: false` in `config.yaml`). It can make low-volume requests without an NCBI key; see [NCBI's API key explanation](https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/). Enabling discovery does not approve articles for clinical answers: those require the reviewed-PMID allowlist. The core PDF/workbook chatbot needs neither NCBI field.

**Neo4j is the local database** holding Graphiti's HCP memory graph and document search vectors. Graphiti builds and queries the memory; the application creates the database indexes. You do not need to create nodes manually. SQLite holds the source registry and consented chat records in the generated `data/` folder.

Start Neo4j with Docker Compose (Windows/macOS/Linux), or point `.env` at an existing Neo4j instance. The following command downloads the configured database image on its first run, creates the local database, and runs it in the background:

```shell
docker compose up -d
```

On Windows without Docker, the included helper is an alternative:

```shell
python scripts/local_neo4j.py setup
python scripts/local_neo4j.py start
```

Use one database option. The helper keeps Java/Neo4j under ignored `.runtime/`, with no Windows service or global Java changes. Docker uses a local named volume. Wait until the following doctor command reports `neo4j_connected: true` before syncing/seeding.

From the activated environment, rebuild and run the pipeline:

```shell
python -m camzyos.cli prepare
python -m camzyos.cli doctor
python -m camzyos.cli sync
python -m camzyos.cli seed
python -m streamlit run app.py
```

`prepare` works offline without secrets: it parses the bundled PDFs and recreates the initial active EMA corpus only when the complete source hash and pipeline-version ID match [the recorded prototype review](assets/demo_review.json). Changed/new versions remain staged for review; previously withdrawn versions are not restored. Prototype eligibility is not sponsor approval. `ingest` remains the stage-only command for ordinary document updates.

`sync` embeds active documents. `seed` imports the eight supplied HCP contexts into isolated Graphiti groups. Both use the configured API and incur usage; repeating an unchanged seed skips its existing episode. Open http://127.0.0.1:8501 and use `anna.weber@example-clinic.de` or another workbook email.

`doctor` should report `workbook_found`, `pdf_folder_found`, `api_key_configured` and `neo4j_connected` as `true`, with `active_chunks: 20` for the bundled initial corpus. It checks configuration/database connectivity, not whether your model API key is valid. Wait for Neo4j to start and rerun `doctor` if its connection is initially false.

### Starting again tomorrow

From the repo folder, activate the same Python environment, start the database using your chosen option (`docker compose up -d` or `python scripts/local_neo4j.py start`), then run `python -m streamlit run app.py`. Keep `.env`, `data/` and the database storage on that machine. You do not need to reinstall, reparse or reseed unchanged inputs on every launch.

For Docker, `docker compose down` stops the database while preserving its named data volume. Changing `NEO4J_PASSWORD` in `.env` later does not change a password already stored in an existing database. If login fails, use the password set during initial setup. A fresh clone on another machine needs its own `.env` and the full first-run pipeline above; it does not inherit your saved conversations.

If PowerShell blocks `Activate.ps1`, run commands with `.\.venv\Scripts\python.exe` instead of `python`; activation is only a convenience. If Docker reports that it cannot connect, start Docker Desktop before running Compose. The optional database browser is http://127.0.0.1:7474 (user `neo4j`, your database password); the chatbot itself is on port 8501.

Without a key, profile loading, lexical retrieval previews, deterministic handoff rules, source review and update staging work. The app labels previews as passages, not generated medical answers. Generated databases, embeddings and runtime packages are rebuilt on the new machine; credentials and real chat histories are not distributed with the repo.

## What is implemented

| Area | Behavior |
|---|---|
| HCP personalization | Deterministic own-profile lookup, personality, last interactions, experience, language, concerns and already-received content; selected context IDs shown with the answer. |
| Graphiti | Per-HCP temporal memory using `group_ids`; consent-gated new memory; assistant-generated clinical claims are not stored as medical facts. |
| Document RAG | PyMuPDF, repeated-margin cleanup, sentence-preserving soft chunks, page/section anchors, Neo4j vector retrieval plus BM25 rank fusion. |
| Source control | Market, audience, account, dates and active-version filtering; immutable PDF snapshots and source metadata. Placeholders never enter clinical retrieval. |
| Grounding | Structured claim/evidence IDs, deterministic citation checks, separate model verification, refusal when support is insufficient. |
| Handoff | Patient-specific, off-label, comparative, privacy, adverse-event, product-quality and human-request routing; short downloadable draft, never automatically sent. |
| PubMed | Off by default; fixed drug/topic queries contain no HCP data; fetched PMID metadata, abstract-only labeling, correction/retraction checks and a reviewed-PMID allowlist. |
| Updates | SHA-256 plus pipeline fingerprint; changed PDFs are reparsed and staged; activation switches versions transactionally. Updates do not trigger outbound messages. |
| Comparison | Same configured model in generic, document-only and contextual modes; no evaluation memory writes. RAGAS clinical faithfulness plus tests and a human-review rubric. |

```mermaid
flowchart LR
    Q[HCP email + question] --> P[Resolve identity and policy]
    P --> H[Own workbook context + Graphiti memory]
    P --> R[Eligible document retrieval]
    R --> A[Structured answer]
    H --> A
    W[Optional reviewed PubMed abstracts] --> A
    A --> V[Claim + scope verification]
    V --> C[Answer with sources and context]
    P --> D[Handoff draft]
    V --> D
```

Graphiti handles interaction memory. `neo4j-graphrag` handles document vectors; SQLite handles transactional source versions and consented transcripts. This avoids treating graph-extracted medical statements as the source of truth. No separate vector service or free-running agent loop is needed.

## Source updates and evaluation

Use **Sources & updates** to upload a replacement or check the configured publisher URL. Inspect the extraction audit before activation, then sync embeddings. Unchanged source bytes and pipeline settings skip parsing. Withdrawn, expired and superseded versions cannot support new answers; historical answers retain their original citations.

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m evals.run --limit 2 --ragas
```

The last command makes paid model calls and writes ignored `reports/comparison.jsonl`. A complete run covers eight profiles × five questions × three modes, starting with the approved-indication question. RAGAS scores clinical claims against evidence; personalization is assessed separately. Report failures and abstentions alongside scores. See [evaluation guide](docs/evaluation.md).

The German Fachinformation currently remains staged because its columns, hyphenation and diagrams need further extraction review. The local active corpus uses the checked EMA SmPC prose, with structured pages excluded. Hospital/payer evidence and explicit account affiliations have not been supplied. These are visible content gaps, not invented context.

## Repository map

- [Discussion context](docs/context.md): the complete product brief, choices and scope from our conversation.
- [Detailed requirements](docs/requirements.md): acceptance cases and intended architecture.
- [Reuse research](docs/reuse-research.md): investigated repositories and why Graphiti was chosen.
- [Source ledger](docs/sources.md): every added source and its contribution.
- [PDF review](docs/document-review.md): supplied corpus review.
- [Implementation status](docs/status.md): verified behavior and remaining limits.

Email entry is synthetic-demo identity selection, not authentication. Source administration is a local reviewer view. Keep this prototype on localhost with the synthetic dataset until verified authentication and application roles are implemented. `assets/` is committed; `.env`, generated `data/`, runtime downloads, transcripts and reports are ignored by Git.
