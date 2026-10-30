# Evaluation method and reproduction

Use the [metrics-only report](evaluation-report.md) for a compact results table and the committed
[evaluation snapshot](evaluation-results.json) for values, denominators, provenance and limitations.
The recorded full benchmark predates later guardrail and presentation changes; it is not a score
for the current application revision.

Testing separates implementation behavior, retrieval, clinical claim support, HCP contextualization
and policy routing. A high grounding score does not establish a correct handoff or useful
personalization. Handoffs and execution/scoring failures remain in reports rather than being silently
discarded. All eight PDFs can be tested through the separate [inspection index](all-pdf-testing.md).

Before model evaluation, run from the activated environment:

```shell
python -m pytest -q
python -m ruff check .
python -m camzyos.cli doctor --strict --all-documents
```

On Windows, `.\.venv\Scripts\python.exe` can replace `python`. Prepare the database and indexes using
the [README](../README.md) if the strict check fails. Evaluation does not save HCP conversation memory.
Keep source versions, model/configuration and HCP seed state fixed within an experiment.

In Streamlit, select the HCP, open **Evaluation**, choose a bundled case and inspect **Reference and
expected source**. Run **Retrieval only**, then **Contextual answer**, with **Score with RAGAS**
enabled; download each result. The page runs one bundled case at a time, without the live Chat
transcript or PubMed. **Compare** displays three fresh response modes but does not calculate scores.

Equivalent repeated CLI measurements:

```shell
python -m evals.retrieval --ragas --repeats 3
python -m evals.retrieval --ragas --answers --repeats 3
python -m evals.retrieval --ragas --answers --case indication --email anna.weber@example-clinic.de
python -m evals.corpus
```

The bundled [cases](../evals/cases.json) contain four questions: indication, ingredient, administration
and storage. References are exact source-checked excerpts linked to immutable eligible passage IDs;
independent clinical review remains pending. Changed sources invalidate references. Repeated runs
measure variability on the same questions, not additional independent question families. Retrieval
mode uses the original question; contextual-answer mode scores retrieval for the rewritten query.

| Metric | Meaning |
|---|---|
| Reference hit@k / recall@k | Presence and coverage of annotated expected passages in retrieved results |
| Mean reciprocal rank | Mean of 1/rank for the first expected passage; zero when absent |
| RAGAS context precision | Whether passages useful for the reference rank ahead of irrelevant passages |
| RAGAS context recall | Whether retrieved context supports the reference information |
| RAGAS faithfulness | Support for generated clinical claim text; does not score routing or the personal introduction |

The full 30 October run measured retrieval precision/recall of 0.964/1.000, and contextual-answer
precision/recall/faithfulness of 0.897/1.000/0.903. Both modes had 12 runs from four distinct questions.
Contextual-answer faithfulness ranged from 0.500 to 1.000. Reports retain each repetition, search
query, reference hash, passages, answer and errors. CLI failure status includes answerable-case
handoffs, missing requested metrics, invalid references and execution errors; low completed scores
remain findings rather than being hidden as execution failures.

The supplied AI-authored HCP challenge file is separate from the bundled source-pinned cases. It
contains 132 scenarios across eight HCPs and 134 actual user turns. It is a separately supplied local
input, not included in this repository. To evaluate a compatible file:

```shell
python -m evals.hcp --cases-file path/to/hcp-cases.json --judge-behavior --ragas
python -m evals.hcp_report reports/hcp-golden-RUN_TIMESTAMP
python -m evals.contextualization --run-dir reports/hcp-golden-RUN_TIMESTAMP --workers 3
python -m evals.context_checks --run-dir reports/hcp-golden-RUN_TIMESTAMP
```

Each scenario needs `id`, `hcp_id`, `hcp_name`, `login_email`, `as_of_date`, `category`, `question`,
`expected_decision`, `expected_behavior`, and string arrays `guardrails`, `expected_sources`,
`grounded_in`. Identity must match the workbook. The runner uses actual generated replies for
follow-ups, not scripted assistant placeholders. See `evals/hcp.py` and its schema tests for details.

That full run produced 36 answers, 96 handoffs and no application execution errors. Faithfulness
averaged 0.911 over the 36 final answers. Reference-based precision/recall were unavailable because
the challenge file has no reviewed clinical reference excerpts. Its AI-authored expectations include
capability/source mismatches; behavioral alignment counts are diagnostic, not validated accuracy.

Own-HCP context was declared by all 36 answers, with no foreign declared context keys or citation-ID
membership failures detected. Only 14/132 outputs matched the recorded German-language target.
Earlier user context was present in both actual follow-up scenarios, with appropriate patient-specific
handoffs on inspection. These are narrow trace/language checks, not proof of semantic personalization.
The separate subjective judge failed calibration; its methodology and recovery rules remain in
[contextualization evaluation](contextualization-evaluation.md).

Evidence review identified a contradiction in `ray_001` despite RAGAS faithfulness 1.0, six missed
Pharmacovigilance routes, unsupported historical-update claims and incorrect refusal rationales.
Subsequent fixes added event precedence, exact-quote scope checks, temporal-evidence limits and
per-claim proof audits. All 15 targeted case checks and four claim-audit checks met their specific
expectations, including routing the six missed reports to PV drafts. One initiation-checklist case
still handed off because verification rejected proof excerpts. These were development regressions;
the full benchmark has not been rerun after the changes. See [status](status.md).

For additional retrieval cases, copy the format of `evals/cases.json`: unique `id`, `question`, exact
`reference`, `reference_ids`, `source_version`, `pages` and `reference_status`. Review the original
eligible PDF passage. The current validator requires the reference excerpt within one annotated
passage; generated answers, workbook placeholders and inspection passages are not clinical gold.

```shell
python -m evals.retrieval --cases-file path/to/dev-cases.json --ragas --answers --repeats 3
python -m evals.retrieval --cases-file path/to/held-out-cases.json --ragas --answers
```

Separate development and held-out question families before tuning; keep translations/paraphrases of
the same question together. Once failures inform a fix, those questions become development material.
Keep legitimate source documents in the RAG corpus: hold out evaluation questions/annotations, not
the evidence needed to answer them. Freeze inputs and retain every outcome for the final measurement.

Boundary evaluation should pair positive and negative controls: reported symptoms versus general
side-effect questions; affirmative off-label requests versus negated mentions; personal treatment
decisions versus general product information; own versus another HCP's data; current label versus
historical-change claims. Include German/English paraphrases, ambiguous follow-ups, explicit style
overrides, prompt injection, missing local policy, unapproved/expired/wrong-market sources, source
withdrawal, absent consent and unavailable services. Review route destination and reason, false
refusals, unsupported acceptance, citation support and useful context separately. UI examples are
in [demo scenarios](hcp-demo-scenarios.md); source-state/consent checks belong in isolated test fixtures,
not by changing a live demonstration's active corpus.
