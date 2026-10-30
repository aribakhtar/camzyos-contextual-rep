# CAMZYOS Contextual Rep

A Streamlit prototype for CAMZYOS product-information questions from healthcare professionals in
Germany. It combines document retrieval with HCP preferences and conversation context, displays its
sources, and prepares a human follow-up draft when policy or evidence prevents an answer.

The repository includes eight synthetic HCP profiles and eight PDFs. Source eligibility is a
prototype review decision, not sponsor approval. The email selector is a demo identity mechanism;
production authentication and external handoff delivery are not implemented.

| Start here | Contents |
|---|---|
| [Product walkthrough](docs/product-walkthrough.md) | Chat, Compare, Evaluation, Context and source management |
| [Demo scenarios](docs/hcp-demo-scenarios.md) | HCP emails, questions, persona comparisons and boundary cases |
| [Architecture](docs/project-flow.md) | Preparation, retrieval, memory, verification and code locations |
| [Evaluation metrics](docs/evaluation-report.md) | Recorded benchmark values |
| [Evaluation method](docs/evaluation.md) | Reproduction, datasets, limitations and guardrail findings |
| [Implementation status](docs/status.md) | Verified behavior and unresolved limitations |

Install Git and Python 3.13. Use Docker Compose for Neo4j, or the portable Windows database helper.

```shell
git clone https://github.com/aribakhtar/camzyos-contextual-rep.git
cd camzyos-contextual-rep
```

On Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements.lock -e '.[dev,eval]'
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
```

On macOS/Linux:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements.lock -e '.[dev,eval]'
test -f .env || cp .env.example .env
```

Edit `.env` locally: set `OPENAI_API_KEY` and choose a `NEO4J_PASSWORD` of at least eight characters.
Keep existing credentials when returning to a configured installation. The bundled input paths and
local database defaults need no changes. Model, embedding, Graphiti and RAGAS calls incur API usage.
Optional NCBI settings are not needed for the core application. Never commit `.env`.

Start **one** database option. With Docker running:

```shell
docker compose up -d
```

Alternatively, on Windows without Docker:

```powershell
.\.venv\Scripts\python.exe scripts/local_neo4j.py setup
.\.venv\Scripts\python.exe scripts/local_neo4j.py start
```

The portable helper keeps Java and Neo4j under ignored `.runtime/`; `setup` is needed only initially.
Changing the password in `.env` does not change credentials in an already initialized database.

On Windows, the preparation-first launcher runs the complete pipeline before opening Streamlit:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1
```

Add `-PrepareOnly` to prepare without launching the UI. On other platforms, use the activated
environment and run the equivalent steps:

```shell
python -m camzyos.cli build
python -m camzyos.cli index-all
python -m camzyos.cli doctor --strict --all-documents
python -m camzyos.cli seed
python -m streamlit run app.py
```

Open <http://127.0.0.1:8501> and select `anna.weber@example-clinic.de`. Try:

> Please answer in English: How should CAMZYOS capsules be taken?

Preparation parses and chunks the PDFs, creates Neo4j embeddings, verifies both indexes and seeds
isolated HCP memory. Compatible existing embeddings and unchanged seeds are reused. The clinical
index currently contains 20 eligible passages; the separate inspection index covers all eight PDFs.
Chat requires a complete clinical index and never parses or embeds document files on a question.
New or changed source versions remain staged until review; see [source coverage](docs/all-pdf-testing.md).

For subsequent launches, start the same database and rerun the launcher or preparation steps above;
unchanged work is reused. Stop foreground Streamlit with Ctrl+C, then stop the chosen database:

```shell
docker compose down
```

Or, for portable Windows Neo4j:

```powershell
.\.venv\Scripts\python.exe scripts/local_neo4j.py stop --timeout 60
```

These shutdown commands preserve database storage. Do not delete the Docker volume to stop the app.

Run checks from the activated environment, or replace `python` with `.\.venv\Scripts\python.exe`
on Windows:

```shell
python -m pytest -q
python -m ruff check .
python -m camzyos.cli doctor --strict --all-documents
python -m evals.retrieval --ragas
python -m evals.retrieval --ragas --answers
```

The last two commands make paid model calls and create local reports. Compare shows outputs from
generic, document-only and contextual modes; Evaluation scores bundled source-linked cases.
Scores are diagnostic, not clinical approval. Known false passes, routing failures and evaluator
limitations remain documented in [evaluation](docs/evaluation.md) and [status](docs/status.md).

| Directory | Responsibility |
|---|---|
| `camzyos/` | Policy, document preparation, retrieval, memory and response verification |
| `app.py` | Streamlit interface |
| `assets/` | Original workbook/PDFs, provenance hashes and recorded prototype source review |
| `evals/` | Evaluation cases, runners and report generation |
| `tests/` | Automated implementation checks |
| `scripts/` | Preparation, startup and portable Neo4j lifecycle |
| `docs/` | Product scope, architecture, usage, sources and evaluation |

The workflow is coordinated directly in Python; it does not use LangGraph. Graphiti manages HCP
memory, Neo4j stores vectors and graph data, and SQLite stores source versions and consented chat
records. Conversation storage is opt-in, and handoffs are downloadable drafts, never automatic sends.
Generated data, runtime downloads, credentials and raw reports are excluded from Git. See
[asset provenance](assets/README.md), [source attribution](docs/sources.md) and [product scope](docs/context.md).
