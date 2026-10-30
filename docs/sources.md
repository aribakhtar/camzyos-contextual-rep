# Source ledger

Reviewed/fetched during the initial build on 30 October 2026. Runtime eligibility is controlled by `sources.yaml` and the local active-version registry. A public source is not automatically sponsor-approved. No placeholder workbook text was promoted into medical evidence.

## Supplied material

The workbook contributes synthetic HCP identities, preferences, personality, interaction history, already-received content, review flags and guardrail requirements. The seven supplied PDFs are listed in [the corpus inventory](all-pdf-testing.md) and `sources.yaml`. At the user's request, all supplied files and the added German PDF are now committed under [assets/](../assets/README.md), with original-byte checksums in [the asset manifest](../assets/manifest.json). The initial build's hash/status inventory is in [source-inventory.json](source-inventory.json).

## Added or independently fetched public material

| Source | Contribution | Runtime treatment |
|---|---|---|
| [EMA CAMZYOS product information PDF](https://www.ema.europa.eu/en/documents/product-information/camzyos-epar-product-information_en.pdf) | Independently downloaded to check the supplied EU label against the publisher. SHA-256 matched the supplied bytes. Provides the professional SmPC prose. | One active prototype version; only scoped professional pages, excluding flagged diagram/table pages. This check establishes byte equality at fetch time, not perpetual currency. |
| [German CAMZYOS Fachinformation, BMS](https://fi.b-ms.de/camzyos) | Additional German-language professional source, 12 pages, labeled May 2025. Adds a source for German wording and future cross-checks. | Downloaded and staged; not activated because multi-column text, hyphenation and diagrams need further review. |
| [EMA CAMZYOS EPAR](https://www.ema.europa.eu/en/medicines/human/EPAR/camzyos) | Publisher landing page and provenance/document discovery during research. | Discovery only; not an extra answer corpus. |
| [EXPLORER-HCM publication, PMID 32871100](https://pubmed.ncbi.nlm.nih.gov/32871100/) | Live connector smoke test fetched its citation metadata and abstract; the record included a correction flag. | Discovery only; requires review and is absent from the approved PMID list. No medical answer was generated from it. |
| [Long-term effect of mavacamten, PMID 39217450](https://pubmed.ncbi.nlm.nih.gov/39217450/) | Second live PubMed smoke-test record, confirming fetched title/PMID/abstract handling. | Discovery only; absence of a correction flag does not approve it. Not added to the answer corpus. |

PubMed output includes canonical URLs, authors, journal, year, DOI when supplied, publication types and correction/retraction flags. Only allowlisted, unflagged, non-empty abstracts can enter an answer when the toggle is on. Full text has not been accessed through this connector. Future public additions must record publisher, version/provenance, eligibility and contribution before activation.

## Technical references

| Source | Contribution |
|---|---|
| [Graphiti repository](https://github.com/getzep/graphiti) and [official sales-agent example](https://help.getzep.com/graphiti/integrations/lang-graph-agent) | Reusable temporal memory, customer-specific retrieval pattern, episodes and scoped `group_ids`; example security/isolation limitations informed the design. We use the library, not a copy of its demo server. |
| [Neo4j GraphRAG retrieval guide](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html) | Vector retriever, filter behavior and citation/result handling. Eligibility is enforced again in application code. |
| [Neo4j construction guide](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html) | Evaluated library ingestion options; the prototype keeps its clinical evidence as document chunks instead of extracted graph claims. |
| [PyMuPDF text recipes](https://pymupdf.readthedocs.io/en/latest/recipes-text.html) | PDF text/layout extraction; page and span positions support conservative margin cleanup. Installed APIs were also inspected. |
| [pySBD](https://github.com/nipunsadvilkar/pySBD) | Library sentence boundaries for soft chunks without arbitrary character cuts. |
| [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs) | Pydantic output schemas for decisions, claims, context IDs and verification; Responses requests use `store=False`. |
| [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/home/develop/api/) and [PubMed help](https://pubmed.ncbi.nlm.nih.gov/help/) | ESearch/EFetch, verifiable citation metadata and correction/retraction handling. |
| [RAGAS faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/) | Evidence-support evaluation semantics; not a substitute for clinical or personalization review. |
| [RAGAS metric definitions](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) and [scikit-learn data-leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage) | Testing workflow separates known development cases from independent held-out question families, retains repeated outcomes, and distinguishes metric completion from answer quality. No clinical sources or reference answers were added from these pages. |
| [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing) | Programmatic UI-flow testing, including identity changes and sidebar views. |
| [Neo4j distributions](https://neo4j.com/deployment-center/) and [Eclipse Adoptium API](https://api.adoptium.net/) | Optional portable local Neo4j/Java runtime. Java archive checksum is checked against publisher metadata. |
| [Official Neo4j Docker image](https://hub.docker.com/_/neo4j) | Cross-platform database option in `compose.yaml`; the `2026.10.1-community` tag was verified through Docker Hub and provides amd64/arm64 images. |
| [Graphiti UUID issue #1646](https://github.com/getzep/graphiti/issues/1646) and [adding episodes](https://help.getzep.com/graphiti/core-concepts/adding-episodes) | Confirmed the installed 0.31.2 create-versus-reprocess behavior. Seed deduplication uses an HCP-scoped deterministic name while Graphiti assigns new episode UUIDs. |
| [Neo4j Windows installation](https://neo4j.com/docs/operations-manual/current/installation/windows/) and [Windows console control handling](https://learn.microsoft.com/windows/console/setconsolectrlhandler) | Portable console startup/shutdown and inherited Ctrl-C behavior; informed the hidden-console wrapper and graceful stop helper. |
| [JDK Attach API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html) and [JVM shutdown sequence](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html) | One-time local recovery of the original JVM that ignored Ctrl-C, invoking normal shutdown hooks rather than force-killing. The normal start/stop workflow does not load an agent. |

These library and design references are technical attribution, not medical evidence. The
implemented boundaries and component responsibilities are documented in [architecture](project-flow.md).

Graphiti is Apache-2.0 licensed. PyMuPDF is provided under AGPL/commercial licensing; consult its [license page](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright) when deciding how to distribute/deploy the application. Dependency licenses remain their authors' licenses. The repository does not relicense supplied documents or copy third-party example source files.
