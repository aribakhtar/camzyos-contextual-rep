# Implementation status

Recorded on 30 October 2026. The prototype runs locally with bundled synthetic HCP data. The
[evaluation guide](evaluation.md) separates the full benchmark, later targeted fixes and UI checks.
Historical values are preserved in the [evaluation snapshot](evaluation-results.json).

| Area | Verified state |
|---|---|
| Software checks | Latest local suite: 344 tests and 14 subtests passed; Ruff passed. One upstream Graphiti/Pydantic deprecation warning remains. |
| Clinical index | 20/20 eligible passages, ONLINE, from the recorded EMA SmPC version |
| Inspection index | 432/432 passages across eight PDFs and 203 pages, ONLINE; all eight corpus smoke checks passed |
| Startup | Document preparation, strict index checks and HCP seeding precede Streamlit through `scripts/start.ps1`; unchanged embeddings/seeds are reused |
| HCP context | Own-profile lookup, personality, dated supplied interactions and scoped Graphiti memory |
| Conversation | Full dated transcript, token-budget summaries of working context, explicit clear/forget, opt-in persistence |
| Retrieval | Vector + BM25 fusion, up to 20 candidates reranked to six, eligibility checks before and after retrieval |
| Grounding | Structured IDs, per-claim proof audits, separate verification and bounded correction |
| Handoffs | Downloadable drafts for policy/evidence boundaries; no external delivery |

The full 132-scenario evaluation produced 36 answers, 96 handoffs and no execution errors. Its
mean faithfulness of 0.911 covers generated clinical answers only. Reference-linked retrieval and
answer metrics are in the [metrics report](evaluation-report.md); these precede the latest fixes.

Review found a cited-source contradiction despite faithfulness 1.0, six missed Pharmacovigilance
routes, unsupported historical-update claims and incorrect off-label rationales. After fixes, 15
targeted case checks and four claim-audit checks met their expectations. The initiation-checklist
case still produced a verification handoff, although its incorrect off-label rationale was removed.
These known regressions are not an independent benchmark or a complete rerun of the updated model flow.

A subsequent three-turn Anna Chat check answered directly without repeated profile introductions,
with citations and retained history. In the Compare rehearsal, a narrow administration question
answered in both grounded modes for Anna, while Prakash's contextual result was withheld. A broader
indication-plus-administration question produced verification handoffs for both HCPs. Reranking
warnings also occurred. These outcomes remain limitations, not evidence of a guaranteed successful demo.

Remaining limitations:

- Email selection is not authenticated identity, and source administration has no production roles.
- The active corpus excludes complex figures/tables and the staged German extraction. Full dosing
  algorithms, verified hospital policies and payer/account evidence are not available.
- No reviewed historical version-comparison workflow, automatic outbound updates or external
  medical/Quality/Pharmacovigilance intake integration exists. A PV draft is not a submitted report.
- Medical-source filtering is not a dedicated promotional-content review workflow. No explicit
  confidential-insight exclusion pipeline or signal layer exists, and retrieval scores are not
  calibrated clinical-confidence probabilities. Source-date checks depend on supplied metadata.
- Consented transcript/provenance storage is not a complete production audit system. Storage consent,
  outbound consent and sharing a handoff remain distinct; identifiable opt-out conversations are
  not automatically persisted to satisfy an audit requirement.
- Model-based verification can miss contradictions or withhold supported answers. Language alignment
  was 10.6% in the full scenario run; fixed English templates and conflicting language instructions
  remain. The subjective contextualization judge failed calibration.
- Conversation summaries can lose or misattribute detail. The original transcript remains available;
  summary presence alone does not establish semantic accuracy.
- API connectivity and latency vary. All response modes depend on configured services; no question
  guarantees an answer or a stronger personalization result.
- Independent clinical review, unseen question-family evaluation and a complete benchmark rerun
  after the latest fixes remain pending.

Raw transcripts, screenshots and machine-specific reports remain under ignored `reports/`. The
committed snapshot contains aggregate values and limitations so a fresh clone can inspect the
recorded results without access to local runtime files.
