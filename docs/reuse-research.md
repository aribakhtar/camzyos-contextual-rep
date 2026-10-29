# Reusable foundations for a profile-specific contextual RAG chatbot

> Design/research record. See [implementation status](status.md) for what is now built, tested and still limited.

Research date: 30 October 2026. Recommendation based on documentation, repository metadata, and selected source-code inspection. No candidate was deployed or benchmarked during this research.

**Decision:** Reuse Graphiti's official personalized sales-agent example and library as the starting point for our Neo4j backend. Keep Streamlit and the evaluation plan. Add explicit profile lookup, controlled document retrieval, access checks, and handoff logic. This recommendation reflects fit with our chosen stack; it is not a claim that Graphiti is universally the best memory system.

The pattern already exists: authenticated customer identity + structured profile + relevant interaction memory + shared product knowledge → contextual response. We do not need to invent the memory infrastructure. I did not verify a complete application that meets every requirement unchanged.

**Strongest candidates**

| Candidate | What already exists | Fit and remaining work |
|---|---|---|
| [Graphiti + official sales-agent example](https://help.getzep.com/graphiti/integrations/lang-graph-agent) | Product catalogue, customer node, retrieval of previous conversation facts, new-interaction persistence, LangGraph workflow, Neo4j | Best fit with our graph approach. Notebook UI, incomplete customer isolation, no application-specific document approval or handoff rules. |
| [Mem0 + official Streamlit RAG tutorial](https://mem0.ai/library/integrations/agentic-rag-chatbot-with-memory) | Document search, separate user-memory search, memory writes, Streamlit, LangGraph | Closest tutorial to the desired UI and dual retrieval pattern. Tutorial uses hosted MemoryClient and Chroma; linked starter repository was inaccessible. Current Neo4j compatibility must not be inferred from old examples. |
| [Memobase + Playground](https://github.com/memodb-io/memobase-playground) | Profile-oriented memory and a full chat template with users and conversation threads | Strong alternative if willing to use its Next.js/Supabase stack. Product-document grounding and our policies still need work. |
| [Hindsight](https://github.com/vectorize-io/hindsight) | Persistent memory banks and retain/recall/reflect operations; Python clients | Good memory-engine alternative. Its deployment uses PostgreSQL; adopting it would add or change storage infrastructure. |
| [LibreChat](https://www.librechat.ai/docs/features/memory) | Complete chat application, user memory, authentication/access-control features, file retrieval | Useful if getting an existing application running is more important than retaining Streamlit. Built-in memory is a small key/value store, not automatic retrieval over historical conversations. |
| [LangChain memory-agent](https://github.com/langchain-ai/memory-agent) | Small MIT-licensed agent template with memories scoped by user ID across threads | Lightweight reference for user-scoped memory. Document retrieval, profile loading, UI and handoff remain to be connected. |
| [Cognee](https://github.com/topoteretes/cognee) | General memory/knowledge framework with ingestion, retrieval, datasets and deployment options | Worth considering for a broader knowledge platform. No closer end-to-end match was established in this review. |

**Why Graphiti is the leading choice**

The official example is a shoe-sales assistant. It loads product JSON, creates a customer node, retrieves facts near that customer, queries product information through a tool, and persists interactions. This demonstrates the same core relationship between a person, previous interactions, and product knowledge that we need. The implementation is available in the [official notebook](https://github.com/getzep/graphiti/blob/main/examples/langgraph-agent/agent.ipynb).

Graphiti provides temporal facts, episode provenance and hybrid retrieval. Its repository has an [Apache-2.0 license](https://github.com/getzep/graphiti/blob/main/LICENSE); the observed last push was 28 October 2026. Recent activity supports considering it, but does not prove reliability for our workload. [Repository and capabilities](https://github.com/getzep/graphiti).

Source inspection identified specific adaptations:

- The notebook uses a fixed sample customer. Replace this with application-resolved identity and deterministic loading of supplied profile fields.
- `center_node_uuid` affects ranking. The example's searches do not pass customer-specific `group_ids`; proximity to a customer is not an authorization boundary.
- It writes assistant replies back into memory. Store those as attributed conversation records; never promote an earlier generated answer into approved product evidence.
- Current session state uses an in-memory checkpointer. Persist sessions deliberately if continuity across application restarts is required.
- The notebook includes a database-clearing setup cell. Do not execute it against an existing database when adapting the example.

These observations come from the [notebook source](https://raw.githubusercontent.com/getzep/graphiti/main/examples/langgraph-agent/agent.ipynb). Its sales-oriented prompt also needs replacement with our informational role and response policy.

The repository explicitly says its reference REST/MCP servers lack authentication, authorization and prompt-injection protection. Use the library behind our application boundary; do not treat those example servers as a finished deployment. [Reference-server limitations](https://github.com/getzep/graphiti#reference-mcp-and-rest-servers).

**Promising demos that are unsuitable as an immediate fork**

| Repository | Useful idea | What inspection found |
|---|---|---|
| [Customer Support Memory Agent](https://github.com/chintalavikas/customer_support_memory_agent) | Streamlit customer selector, seeded customer profiles and dated history, memory-on/off comparison, displayed recalled memories | No license file in the inspected tree. Single-turn generation; stores unverified assistant replies. No document-grounding pipeline or evaluation harness. |
| [Customer Support AI Copilot](https://github.com/Nihal108-bi/customer-support-ai-copilot) | Streamlit/FastAPI, policy RAG, customer memory, human acceptance of drafts, context-used display | No license file in the inspected tree. Source stores/searches accepted resolutions in both customer and company scopes when a company exists. That sharing would conflict with isolated HCP histories unless redesigned. |
| [Memory-Augmented Chatbot](https://github.com/jaagam751-stack/memory-augmented-chatbot) | Streamlit, Neo4j, LangGraph, document retrieval, user memory | No license file in the inspected tree. User memory is JSON with regex extraction; graph retrieval does not take a user scope and matches entities by name. Same technology names do not establish the required behavior. |
| [ResolveX AI](https://github.com/VishnuAIHRschool/resolvex-ai-multi-agent-system) | README describes layered customer memory, hybrid RAG, guardrails, review and a Streamlit application | API detected no license. README describes a buildathon application with mandatory three-agent execution and simulated generation by default. README-level review only; its quality claims were not independently verified. |

For the first three, selected implementation files were inspected, not just screenshots. Sources: [memory-agent loop](https://github.com/chintalavikas/customer_support_memory_agent/blob/main/agent.py), [copilot service](https://github.com/Nihal108-bi/customer-support-ai-copilot/blob/main/customer_support_agent/services/copilot_service.py), [JSON memory](https://github.com/jaagam751-stack/memory-augmented-chatbot/blob/main/app/memory/memory_store.py), [Neo4j queries](https://github.com/jaagam751-stack/memory-augmented-chatbot/blob/main/app/knowledge_graph/neo4j_graph.py).

The customer-support demo's comparison design is useful: same customer question and model, with memory enabled or disabled. We can independently implement that evaluation pattern. Missing licensing means these repositories are not cleared reuse foundations merely because their code is publicly visible.

**Other existing applications and commercial products**

- **LibreChat:** Its documented memory stores explicitly saved user facts and injects the store into requests. It does not automatically search old conversations. Its separate file-search feature retrieves document passages and can display sources. This is a substantial application base, but still needs our contextual retrieval and policies. [Memory](https://www.librechat.ai/docs/features/memory), [file RAG](https://www.librechat.ai/docs/features/rag_api).
- **Open WebUI:** Has personal memory features. Its current license includes branding conditions and specific exceptions; it is not interchangeable with a plain MIT license. It also replaces our intended frontend. [Memory documentation](https://docs.openwebui.com/features/chat-conversations/memory/), [license](https://github.com/open-webui/open-webui/blob/main/LICENSE).
- **Dify:** A configurable application/workflow platform to consider if changing the stack. Its license adds conditions concerning multi-tenant workspaces and frontend branding. I did not establish that its default conversation memory satisfies persistent customer-profile retrieval. [Repository](https://github.com/langgenius/dify), [license](https://github.com/langgenius/dify/blob/main/LICENSE).
- **Intercom Fin:** The commercial pattern is already available: customer/company attributes determine available knowledge, guidance, connectors and escalation rules. This is an existing platform to configure, rather than code to reuse inside our stack. [Official audience and personalization documentation](https://www.intercom.com/help/en/articles/9357948-manage-audiences-for-fin-and-copilot).
- **Salesforce Agentforce:** Official examples combine purchase history with company knowledge for personalized service. It is a platform choice with CRM integrations, not a Streamlit/Neo4j starter. [Official product explanation](https://www.salesforce.com/eu/agentforce/how-it-works/).

**Version and availability findings that change the decision**

1. Mem0's older open-source graph-memory URL currently redirects to platform documentation describing a native graph and the replacement of the earlier external graph-store integration. Old Neo4j notebooks remain in its tree. Therefore, selecting current Mem0 on the assumption of unchanged Neo4j support would require a version-specific compatibility check. Its current OSS overview documents vector-store defaults for library/server operation. [Graph-memory page](https://docs.mem0.ai/platform/features/graph-memory), [OSS overview](https://docs.mem0.ai/open-source/overview).
2. The Mem0 Streamlit tutorial links `BexTuychiev/mem0-chatbot-starter`; its GitHub API request returned 404. Inline tutorial material remains accessible, but I could not verify the linked starter as a cloneable public repository. [Tutorial](https://mem0.ai/library/integrations/agentic-rag-chatbot-with-memory).
3. Letta's original repository now points to `letta-ai/letta-code`; its old V1 server is on an archive branch. Older comparisons recommending the original Python server as the current implementation would be misleading. [Current migration notice](https://github.com/letta-ai/letta), [current source](https://github.com/letta-ai/letta-code).
4. Memobase Playground is a licensed full application template, but its last observed push was August 2025. Memobase itself was last pushed in January 2026. Dependency compatibility needs validation before choosing it. [Playground](https://github.com/memodb-io/memobase-playground), [memory service](https://github.com/memodb-io/memobase).

**Proposed reuse boundary for our prototype**

| Component | Reuse or implement |
|---|---|
| Streamlit chat, user selector and evidence/context panels | Thin application-specific UI. The eight-person demo selector is not production authentication. |
| Conversation memory, temporal retrieval | Reuse Graphiti library and adapt its official agent example. |
| Supplied profile, consent, received content and open follow-ups | Import explicitly and retrieve by authenticated user ID. Do not ask an LLM to reconstruct known spreadsheet fields. |
| Authoritative product-document retrieval | Preserve original chunks and source metadata. Use Neo4j retrieval directly or its official GraphRAG package; adding a second memory framework is unnecessary. |
| Eligibility and access controls | Implement deterministic scope, approval, market, audience and validity filtering before retrieval. |
| Grounded response | Combine relevant personal context with eligible source passages, preserving distinct provenance for each. |
| Handoff | Implement trigger checks and a structured summary with question, relevant context, sources, unresolved issue and destination. |
| Evaluation | Retain RAGAS plus custom isolation, citation, memory and handoff checks, with human review. |

The document retrieval package is a separate optional helper, not an alternative memory system. [Official Neo4j GraphRAG Python documentation](https://neo4j.com/docs/neo4j-graphrag-python/current/).

The central rule is that personal memory changes relevance and presentation; clinical claims must be supported by eligible evidence. A previous assistant reply or inferred graph relation is not sufficient evidence for a clinical claim. No inspected framework provides a guarantee of zero hallucinations.

Before expanding the prototype, validate a small slice: two contrasting profiles, shared product documents, previous interactions, and a fresh chat session. Test profile-specific answers, a corrected preference, no cross-user retrieval, source citations, expired/absent evidence, and a handoff. Use the same model and question for generic, document-only RAG and contextual RAG comparisons. These are proposed checks, not completed results.

**Repository screening ledger**

Dates below are GitHub API `pushed_at` dates observed during research, not release dates or proof of maintenance quality. License labels are API results unless a license file was additionally read. A missing API license is recorded as unknown, not as a definitive legal classification.

| Repository | License observed | Last push | Depth |
|---|---|---|---|
| [getzep/graphiti](https://github.com/getzep/graphiti) | Apache-2.0; file read | 2026-10-28 | Metadata, tree, README, notebook and example source |
| [mem0ai/mem0](https://github.com/mem0ai/mem0) | Apache-2.0; file read | 2026-10-29 | Metadata, tree, README, notebook and current docs |
| [topoteretes/cognee](https://github.com/topoteretes/cognee) | Apache-2.0 | 2026-10-29 | Metadata and README |
| [memodb-io/memobase](https://github.com/memodb-io/memobase) | Apache-2.0 | 2026-01-11 | Metadata, tree and README |
| [memodb-io/memobase-playground](https://github.com/memodb-io/memobase-playground) | MIT | 2025-08-18 | Metadata and README |
| [letta-ai/letta](https://github.com/letta-ai/letta) | Apache-2.0 | 2026-10-18 | Metadata and migration README |
| [letta-ai/letta-code](https://github.com/letta-ai/letta-code) | Apache-2.0 | 2026-10-29 | Metadata and README screening |
| [vectorize-io/hindsight](https://github.com/vectorize-io/hindsight) | MIT | 2026-10-29 | Metadata and README |
| [langchain-ai/memory-agent](https://github.com/langchain-ai/memory-agent) | MIT | 2026-10-28 | Metadata, tree, README and graph source |
| [langchain-ai/langmem](https://github.com/langchain-ai/langmem) | MIT | 2026-10-28 | Metadata and README |
| [LibreChat-AI/LibreChat](https://github.com/LibreChat-AI/LibreChat) | MIT | 2026-10-29 | Metadata and official feature docs |
| [langgenius/dify](https://github.com/langgenius/dify) | Custom; file read | 2026-10-29 | Metadata and license screening |
| [open-webui/open-webui](https://github.com/open-webui/open-webui) | Custom; file read | 2026-10-29 | Metadata, memory docs and license |
| [chintalavikas/customer_support_memory_agent](https://github.com/chintalavikas/customer_support_memory_agent) | No license found in tree | 2026-09-30 | Metadata, tree, README, agent and UI source |
| [Nihal108-bi/customer-support-ai-copilot](https://github.com/Nihal108-bi/customer-support-ai-copilot) | No license found in tree | 2026-07-28 | Metadata, tree, README, service and memory source |
| [jaagam751-stack/memory-augmented-chatbot](https://github.com/jaagam751-stack/memory-augmented-chatbot) | No license found in tree | 2026-07-11 | Metadata, tree, README, memory and graph source |
| [CHETAN-KAURAV/Conversational-Memory-RAG](https://github.com/CHETAN-KAURAV/Conversational-Memory-RAG) | Unknown | 2026-07-30 | Metadata and README screening |
| [shlok-dadhich/Chatbot_rag_long_term_memory](https://github.com/shlok-dadhich/Chatbot_rag_long_term_memory) | Unknown | 2026-06-20 | Metadata and search screening |
| [VishnuAIHRschool/resolvex-ai-multi-agent-system](https://github.com/VishnuAIHRschool/resolvex-ai-multi-agent-system) | Unknown | 2026-07-13 | Metadata and README |

**Search coverage and evidence files**

Searches covered personalized RAG, customer-profile chatbots, sales agents, persistent user memory, customer-support copilots, Streamlit memory demos and Neo4j contextual retrieval. Representative queries included `github personalized RAG chatbot customer profile memory Streamlit`, `site:github.com customer profile Streamlit RAG memory Neo4j`, and `site:github.com personalized chatbot Graphiti`.

Methods: built-in web search and official-page retrieval; GitHub REST repository metadata and recursive trees; direct `raw.githubusercontent.com` source retrieval. Selected raw source files, tree snapshots and the two repository-metadata JSON files are saved alongside this report. Downloaded application code was inspected as text and not executed.

Direct Google HTML retrieval through `webcmd web fetch` returned an unusable fallback page. The Google/GitHub webcmd plugins were discovered and installed, but their commands did not become available; installation reported the missing `esbuild` dependency. Research continued through web search and direct GitHub APIs. Some GitHub browser-page fetches failed; direct raw-file retrieval supplied the relevant code. The Mem0 starter 404 remained unresolved. No claim is made that every search engine or every relevant repository was exhaustively covered.

This is a broad reuse assessment, not a runtime benchmark, security audit or clinical validation. The strongest next implementation target is the official Graphiti sales example adapted to our explicit identity, evidence and handoff requirements.
