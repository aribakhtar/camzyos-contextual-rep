# Verification on 6 November 2026

The [16 user-specified guardrails](guardrails.md) now determine routing and source eligibility.
There are no response word, sentence or claim-count limits. HCP preferences shape the answer;
explicit user requests override defaults. Risk-first profiles order existing safety claims before
other claims, without adding unrelated risks or removing qualifications.

| Check | Result |
|---|---|
| Offline regression suite | 441 tests and 14 subtests passed |
| Ruff | Passed |
| All eight PDF inspection/retrieval checks | 8/8 passed; sampled inspection passages rank 1 |
| Chat source eligibility | Eligible references found; all six excluded sources remained excluded |
| Live definition questions | 8/8 HCPs answered, including Anna and Prakash's `what is camzoys` |
| Live approved-use and safety questions | 8/8 HCPs answered with support, completeness and personality checks |
| Prakash explicit detailed/English override | Passed |
| Rule-specific escalation / review / missing-source cases | 8/8 passed |
| Headless Chrome | Anna and Prakash answers, plus MI, PV, Quality and MSL handoffs passed |
| Current index | 432/432 passages across eight PDFs; 84 passages currently eligible |

The live figures combine the latest result for each case after fixes, rather than claiming every
intermediate run passed. The [case manifest](verification-2026-11-06.json) records result locations,
decisions, targets, source IDs and selected presentation. Full outputs, failed intermediate runs,
claim-audit traces and screenshots remain in ignored local `reports/`. The corpus report is
`reports/all-pdf-smoke-20261106T072137305779Z.jsonl`.

Observed problems and corrections:

- Conflicting default language/detail preferences could override an explicit user request in the
  reviewer. Resolved preferences now have a separate review, with explicit overrides taking priority.
- A definition could be rejected for lacking unrelated team-planning detail. Personality review
  now evaluates only preferences relevant to the actual question.
- PDF line wrapping fragmented proof sentences. Sentence selection now ignores wrapping while
  copying the original source bytes. Malformed structured audits receive one bounded retry;
  unsupported or contradictory verdicts are never retried just to obtain approval.
- A correction could repeat unsupported additions. Feedback identifies those exact claims. A final
  review can retain only unchanged proven claims and must still establish full question coverage.
- Safety-heavy retrieval could omit approved-use evidence in a multipart question. Focused queries
  and interleaved results now retain each requested topic; independent review checks completeness.
- General medical questions could be misclassified as promotional or human requests. Classification
  now follows one explicit rule table, with promotional intent checked against the actual request.

Definitions use the recorded German preference unless the user explicitly requests another language.
The shared broader question requests English. Broad answers and detailed overrides take longer than
simple definitions because they retrieve and audit more evidence. Timings are in the manifest.

These are software regressions and model-based quality checks, not sponsor approval or proof of
perfect medical accuracy/personality interpretation on every future question. Low-confidence or
unsupported responses still invoke GR_11/GR_15 as requested. One upstream Graphiti/Pydantic
deprecation warning remains in the test run.

Escalations and AE/QA intake are durably logged locally. External sponsor systems are not connected;
local case records explicitly remain pending external submission. The app does not claim delivery.
