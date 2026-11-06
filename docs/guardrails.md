# Guardrails and escalation

The policy is the user's GR_01 through GR_16 table. A semantic intent classifier handles
paraphrases; deterministic checks handle clear reports and requests before answer generation.
A keyword shared with a rule is not sufficient: general adverse-effect questions are allowed,
while actual or suspected event reports take the Pharmacovigilance path.

| Rule | Trigger | Action | Escalation target |
|---|---|---|---|
| GR_01 | Off-label question detected | Block generation; issue MI referral message | Medical Information |
| GR_02 | Adverse event mentioned | Answer suppressed; AE intake path triggered; log within 24h | Pharmacovigilance |
| GR_03 | Product complaint mentioned | Route to QA intake | Quality |
| GR_04 | Individual patient advice | Decline individualised advice; offer MSL | MSL |
| GR_05 | Comparative claim requested | No comparison generated; offer approved evidence + MSL | MSL |
| GR_06 | Content expired | Exclude from retrieval | - |
| GR_07 | Content not approved | Exclude from retrieval | - |
| GR_08 | Audience mismatch | Exclude from retrieval | - |
| GR_09 | Market mismatch | Exclude from retrieval | - |
| GR_10 | Promotional / medical boundary | Restrict to medical sources; flag for review | Medical |
| GR_11 | No approved source above threshold | Decline to answer; offer human | Rep or MSL |
| GR_12 | Proactive outbound without consent | Suppress proactive message | - |
| GR_13 | Confidential insight | Exclude from signal layer entirely | - |
| GR_14 | Human explicitly requested | Immediate handoff with summary | Rep or MSL |
| GR_15 | Low answer confidence | Ask clarifying question or escalate | Rep or MSL |
| GR_16 | Audit trail | Persist question, sources, decision, user, timestamp | - |

`camzyos/guardrails.py` is the rule registry. Handoffs carry the rule ID, action, destination,
question and summary. GR_10 permits a factual answer using medical sources and creates a
Medical review record. GR_15 uses clarification or a Rep/MSL escalation when a supported,
context-appropriate answer cannot be verified after a bounded correction. If an extra assertion
remains unsupported, only unchanged proven claims may enter a final review; the result must still
answer the whole question, retain essential qualifiers and pass the personality check.

All eight PDFs remain indexed. Chat filters approval, validity dates, audience, market and
account access before vector and keyword retrieval, after reranking and before releasing citations.
The configured source/page eligibility is the prototype's approval registry; it is not a claim
of sponsor approval. Sources marked `eligible: false` are not silently promoted. The current
snapshot has 432 indexed passages, of which 84 from two sources are eligible for German HCP chat.
Unreviewed page ranges remain excluded. Source metadata changes require rebuilding the index.

GR_11 uses `retrieval_min_relevance: 2` on a 0-3 relevance scale. When reranking is disabled,
`retrieval_min_keyword_matches: 1` applies instead. A scoring outage invokes GR_15; an empty
eligible result invokes GR_11. Claim support and personal factual support are confidence checks,
not additional clinical prohibitions. Update questions go through retrieval normally; unsupported
before/after claims cannot be inferred from a single current source.

There are no answer word, sentence or claim-count limits. The HCP's recorded preferences and
personality shape depth, tone, organization and relevant emphasis. Explicit language, detail
and format requests override defaults. A separate review checks the actual response against
those preferences and can request a correction. This is model-based assessment, not a proof of
perfect personality interpretation for every possible question.

GR_16 always writes question, selected user/email, source IDs/versions, decision, rule IDs and UTC
timestamp to SQLite `policy_audit`, including when chat-memory saving is off. Audit records do not
become Graphiti signals or conversation history. Confidential insights are excluded from profile
signals and Graphiti writes/recall. Proactive generation without outbound consent is suppressed;
no outbound sending integration is installed.

Escalations are recorded atomically with the audit in `escalation_cases`. AE intake is logged
immediately with a 24-hour due time; complaints create a Quality intake. The UI shows the intended
team and provides the handoff summary. These are durable **local intake records**, with
`pending_external_submission` status. External sponsor PV, QA, Medical and MSL systems are not
connected; the app does not claim that those teams received a case. The 24-hour timestamp is
not an external submission scheduler or delivery guarantee.

Optional chat memory remains opt-in. Clear/Forget controls remove their stated chat/memory data;
they do not silently erase the mandatory audit or escalation queue.
