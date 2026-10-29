# Product context retained from the discussion

## Problem and intended experience

A pharmaceutical representative has deep product knowledge but limited availability. An HCP may have a CAMZYOS question while preparing for clinical work and otherwise search independently using an ungrounded assistant. This product provides accessible product information with the context a representative would remember, and a clear route to a human when the question requires one.

Personalization is a core requirement, as important as retrieval. The answer should reflect specialty, experience, practice setting, communication preferences, relevant persona concerns, earlier meetings, prior questions, supplied information and material already received. It must not merely insert the HCP's name into a generic answer. A request for concise information changes presentation; it does not remove essential safety qualifications or change the evidence.

Scope is CAMZYOS in Germany, HCP users, text chat only. UI polish, avatars and voice are out of scope. A general discussion of practice constraints is different from recommending treatment for an individual patient; the latter requires handoff.

## Data provided

The workbook is named `Copy of BMS_ContextualAIRep_Hackathon_Dataset_28th Oct 1.xlsx`. Its local location and the supplied `product information 1` PDF folder are configured in `.env`. The repository deliberately does not embed machine-specific paths or redistribute the raw materials.

The actual workbook contains eight synthetic HCPs, eight personality records and 41 interaction records. Tabs discussed include README, Data_Dictionary, HCP_Profile, Personality, HCP_Interactions, Approved_Content, Content_Chunks, Local_Market_Context, Publications, Updates, Evidence_Gaps, Question_Types and Guardrails. The narrative initially described 11 sheets; actual sheet names and rows control import, rather than that count.

- HCP_Profile, Personality and HCP_Interactions are contextual data, including dated records and known material history.
- Clinical text in Content_Chunks, publications and local-market summaries is synthetic/placeholder. It is excluded from real clinical evidence.
- Approved_Content records do not establish approval of unrelated files or a newly fetched publication. Source eligibility must be established separately.
- Evidence_Gaps are dataset review flags. They prompt caution and follow-up, not claims that no real-world research exists.
- Guardrails and Question_Types inform application behavior and testing; document text cannot override application policy.
- Updates are synthetic until supported by an actual source-version comparison. Do not generate a real clinical change notification from a placeholder row.

The supplied seven PDFs contain 191 pages. Some are US prescribing information and some EU documents mix professional and patient sections. Jurisdiction and section filtering are essential. An additional German Fachinformation was fetched from the publisher and retained locally for review.

## Required behavior

Known email → resolve HCP ID → own context only → name greeting. Unknown email → general eligible content only, no personal/account context and no persistence. The synthetic email selector is a demo convention; production needs verified authentication.

An answer combines the current question, relevant own-HCP context, past interactions, German-market/product context, eligible evidence and optionally reviewed public information. It displays the exact sources and the personal context actually used. Already-received material may be referenced but should not be automatically resent. The current explicit request can override stored presentation preferences for that turn.

Three information categories must remain distinguishable:

1. HCP context: preferences, specialty, experience, practice and interaction history.
2. Brand evidence: applicable label, approved evidence, scientific publications and trials. FDA material is not a substitute for the German/EU label.
3. Account/provider/payer context: verified hospital or clinic policies, pathways and access information linked to an explicit account. Workplace type alone is insufficient.

Off-label questions, advice for an individual patient, unsupported comparative claims and other-HCP information require refusal/handoff. Workbook rules also identify Pharmacovigilance, product-quality and human-request routes. A handoff explains the reason and offers a short question/conversation summary for review. The prototype creates a downloadable draft; it does not contact anyone.

New conversation storage and Graphiti writes need a separate opt-in. Existing proactive-outbound consent does not authorize transcript storage. No proactive outreach is implemented. Updating documents must not imply permission to notify HCPs.

## Technology choices and why

The user proposed Graph RAG + RAGAS + Streamlit, asked for broad reuse research, and specifically selected Graphiti as the memory foundation. The official Graphiti sales-agent example demonstrates personal memory plus product retrieval, but does not supply the required clinical PDF eligibility, versioning, citations, isolation or evaluation. Reuse its library/pattern; do not execute its destructive demo reset cells.

Use Python, Streamlit, Graphiti/Neo4j, PyMuPDF, a sentence segmenter, controlled document retrieval and RAGAS/custom evaluations. Prefer libraries and a short explicit workflow over a framework-heavy autonomous system. No new graph-extraction framework is being built. Canonical workbook fields are read deterministically; Graphiti adds attributed temporal memory rather than replacing those records.

The user requested an actual GitHub repo, an ignored `.env` for their key, a non-secret config file, sentence/word-preserving soft chunks, repeated header/footer cleanup and retention of this discussion in the repo. Keep meaningful section titles and clinical footnotes; blindly deleting all top/bottom text would lose evidence.

For updated documents, hash source bytes and extraction settings, stage new parsed chunks, review, and switch the active version atomically. Keep old snapshots/citations auditable and exclude invalid versions. An on-demand publisher check is sufficient for this iteration; a scheduled watcher is not implemented.

Optional PubMed search is configurable and off by default. Query fixed medical topics without personal details, fetch verifiable records, flag corrections/retractions and distinguish abstracts from full text. Public availability does not automatically confer approval for an HCP-facing answer. Every added source and its contribution must be recorded.

## How the project will be judged

**Grounded:** claims trace to eligible source passages; no invented references, placeholder clinical assertions or off-label advice. Guardrails must be exercised, not merely described in a prompt.

**Contextual:** presentation and relevance visibly use the correct HCP's preferences/history/market. Compare a generic model, document-only RAG and contextual RAG with the same configured model and a fixed corpus. Do not manufacture an improved baseline comparison.

**Useful:** cardiologists can find supported product information, see the source and understand when a human is needed. Compliance reviewers can inspect source versions, context usage and decisions.

**Learning value:** identify missing evidence, extraction limitations, source conflicts, missing account policies and evaluation failures. RAGAS is a measurement aid, not a compliance certificate or a guarantee of zero hallucinations.

The user will supply the model key locally. No key or live clinical benchmark was available during the initial build. Real institutional policies, production identity/roles, sponsor approval decisions and externally connected handoffs remain outside the supplied inputs.
