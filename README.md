# CAMZYOS Contextual Rep

A Streamlit prototype for personalized CAMZYOS information for HCPs in Germany. It combines the supplied HCP workbook, Graphiti memory, and separately controlled document retrieval. Every generated clinical claim must reference retrieved evidence; unsupported requests produce a handoff draft.

**Current state:** runnable locally, with deterministic tests and live source checks. Add your API key for generation, embeddings, Graphiti extraction and RAGAS scoring. No live answer-quality improvement is claimed yet. See [verification and limitations](docs/status.md).

## Clone and run

**The inputs are included in Git:** [assets/hcp_context.xlsx](assets/hcp_context.xlsx) is the original workbook, and [assets/product_information](assets/product_information) contains all seven supplied PDFs plus the downloaded German Fachinformation. You do not need the original Desktop/Downloads folders. See [asset provenance and workbook usage](assets/README.md).

Use Python 3.13 for the locked environment. Clone this private repo using your GitHub access:

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

Start Neo4j with Docker Compose (Windows/macOS/Linux), or point `.env` at an existing Neo4j instance:

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

The last command makes paid model calls and writes ignored `reports/comparison.jsonl`. A complete run covers eight profiles × four questions × three modes. RAGAS scores clinical claims against evidence; personalization is assessed separately. Report failures and abstentions alongside scores. See [evaluation guide](docs/evaluation.md).

The German Fachinformation currently remains staged because its columns, hyphenation and diagrams need further extraction review. The local active corpus uses the checked EMA SmPC prose, with structured pages excluded. Hospital/payer evidence and explicit account affiliations have not been supplied. These are visible content gaps, not invented context.

## Repository map

- [Discussion context](docs/context.md): the complete product brief, choices and scope from our conversation.
- [Detailed requirements](docs/requirements.md): acceptance cases and intended architecture.
- [Reuse research](docs/reuse-research.md): investigated repositories and why Graphiti was chosen.
- [Source ledger](docs/sources.md): every added source and its contribution.
- [PDF review](docs/document-review.md): supplied corpus review.
- [Implementation status](docs/status.md): verified behavior and remaining limits.

Email entry is synthetic-demo identity selection, not authentication. Source administration is a local reviewer view. Keep this prototype on localhost with the synthetic dataset until verified authentication and application roles are implemented. `assets/` is committed; `.env`, generated `data/`, runtime downloads, transcripts and reports are ignored by Git.
