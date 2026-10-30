# Product scope

The assistant provides text-based CAMZYOS product information for HCPs in Germany. It combines
eligible document evidence with relevant HCP preferences and conversation context, with visible
citations and a human-handoff path. Personalization changes relevance and presentation, not the
clinical facts or required safety qualifications.

| Information | Allowed use |
|---|---|
| HCP workbook and own-HCP Graphiti memory | Preferences, experience, concerns, attributed history and material already received |
| Eligible active document passages | Clinical and product claims with exact source/page/version references |
| Account documents | Only when verified evidence and an explicit HCP-to-account mapping exist |

The bundled workbook contains eight synthetic profiles, eight personality records and 41 historical
interactions. Historical dates describe supplied records, not necessarily earlier use of this app.
Its placeholder clinical chunks, publications, local-market summaries and updates are excluded from
medical evidence. All eight PDFs are available for inspection; only the reviewed active clinical
corpus may support answers. See [source coverage](all-pdf-testing.md) and [provenance](sources.md).

Known emails resolve to their own HCP context. Unknown emails receive general eligible information
without personal context or persistence. The selector is a local demo convention, not authentication.
HCP identity scopes live transcripts, caches, stored records, Graphiti groups and exports.

Preferences should quietly shape organization and detail. The current question can override a stored
presentation preference. Avoid routine profile recaps; mention supported personal facts only when
requested or useful. `context_used` records facts and preferences actually applied, including silent
style adaptation. It is an audit trace, not a required introduction.

Full dated conversations remain available in the session. Automatic summarization compacts only
model input when the context budget approaches capacity; it does not delete original messages.
Persistence needs a separate opt-in. Previously unsaved turns must not be saved retrospectively by
later enabling storage. Clear and Forget are explicit controls. Proactive-outbound consent in the
workbook does not authorize storing new chats; no proactive messaging is implemented.

Off-label recommendations, individual treatment advice, comparative product claims and other-HCP
data require refusal or handoff. Reported adverse events take priority and route to Pharmacovigilance;
product complaints route to Quality. Human requests create an immediate draft. Missing eligible
evidence or failed verification can also prevent an answer. Drafts include a reason and conversation
summary for review; the app does not send them or register external cases.

Graphiti supplies attributed memory, not clinical truth or workflow orchestration. Document
eligibility, query rewriting, reranking, working-context summaries and answer verification remain
application responsibilities. The implemented design is in [architecture](project-flow.md); its
verified behavior and limitations are in [status](status.md).
