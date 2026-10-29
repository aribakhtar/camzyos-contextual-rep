# Evaluation guide

Run `python -m pytest -q` and `python -m ruff check .` before model evaluation. These cover policy boundaries and implementation behavior; they do not measure clinical answer quality.

## Preparation and interactive testing

Run `python -m camzyos.cli build` once, then `python -m camzyos.cli doctor`. Require `retrieval_index.ready: true` before testing. Document parsing/chunking/embedding is a preparation operation; chat embeds only its search query and requires the complete document index. No BM25-only fallback is allowed.

In Streamlit, open **Evaluation**. Choose a case, select **Retrieval only** or **Contextual answer**, enable **Score with RAGAS**, and click **Run evaluation**. The page shows the actual query, reference, metrics, failures and ranked passages, with a JSON download. It does not save HCP chat memory. A retrieval-only test uses the question directly; an answer test evaluates the actual retrieval query rewritten by the answer workflow. Those may rank passages differently and must not be conflated.

Equivalent commands:

```shell
python -m evals.retrieval --ragas
python -m evals.retrieval --ragas --answers --case indication
```

The first runs four source-pinned retrieval cases. The second also generates an answer and scores clinical faithfulness. Reports use timestamped paths under `reports/`; `--output` overrides the path. `--email` selects the synthetic HCP. Metric errors, undefined scores and stale references are recorded and produce a non-zero CLI exit; a completed metric with a low score is a finding, not an execution error.

| Metric | Meaning |
|---|---|
| Reference hit@k | Whether a pinned expected passage appears in the returned results. |
| Reference recall@k | Fraction of annotated expected passages retrieved; annotations are a limited prototype set. |
| Reciprocal rank | 1/rank of the first expected passage; zero when absent. |
| RAGAS context precision | Whether passages useful for the reference are ranked before irrelevant ones. |
| RAGAS context recall | Whether retrieved context supports the reference information. |
| RAGAS faithfulness | Whether the generated clinical assertions are supported by retrieved context; unavailable for retrieval-only runs. |

The references in [cases.json](../evals/cases.json) are exact excerpts from the supplied EMA PDF, checked against their immutable chunk IDs. They are not model-generated gold answers or independently clinician-approved references. Source changes invalidate them until reviewed. These narrow questions do not cover all safety, dosing, personalization or German-language cases. Numeric RAGAS scores can vary and need manual inspection; the installed metrics may return no explanatory traces.

Official metric references: [context precision](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/), [context recall](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/). These supplied the metric definitions and collections API usage, not medical content.

## Comparisons

Run `python -m evals.run --limit 2 --ragas` for an initial live check, then remove `--limit` for eight HCPs × five questions × three modes. The first case is "What is CAMZYOS approved for in Germany?" Set the key first. The runner records the configured model, HCP ID, question, timestamp, active source versions, actual output, context, citations and decision. It refuses to continue if the active corpus changes. It does not store evaluation chats as HCP memory and disables live PubMed search for the comparison.

The three modes are generic model, document-only RAG, and contextual RAG. All use the same configured model and early policy checks. Document-only/contextual retrieval has identical source permissions; the contextual answer also receives the correct profile and interaction memory. Model calls are stochastic; repeat runs and report variability before claiming an improvement. The generic column is explicitly unverified evaluation output.

RAGAS `Faithfulness` scores the generated **clinical claim text** against the retrieved document passages. Personal introductions are not scored against medical documents. Context correctness and usefulness need their own review; mixing profile facts into medical grounding would obscure errors. Faithfulness does not establish correct source eligibility, completeness, clinical validity or safe personalization.

## Human scoring sheet

For each answer, record the following with the reviewer, reason and exact offending claim if any:

| Criterion | Suggested scoring |
|---|---|
| Clinical claim support | Supported claims / all clinical claims; assess numbers, negations, qualifiers and cited page. |
| Citation validity | Every ID exists in the retrieved eligible version; the cited passage supports that claim. |
| HCP correctness | No invented, stale-as-current or foreign personal facts. |
| Meaningful personalization | 0: none, 1: superficial, 2: relevant history/style, 3: relevant history/style with preserved safety and useful focus. |
| Clinical consistency | Equivalent questions across profiles keep the same factual core. |
| Completeness/usefulness | 0–3; judge whether the answer addresses the permitted question and exposes meaningful limits. |
| Handoff correctness | Appropriate route and concise draft; no prohibited advice included. |
| Abstention | Supported by a real content/scope gap, or an unnecessary refusal that needs improvement. |

Treat foreign-HCP leakage, fabricated source IDs, placeholder clinical claims, wrong-market evidence and prohibited advice as failures independent of aggregate scores. Report denominator, failure counts, abstention rate and missing-data cases. No-key previews and API errors are not successful clinical answers and must not silently inflate averages.

## Additional live cases

Test German/English paraphrases, concise versus detailed HCPs, explicit style overrides, an irrelevant old meeting, an unavailable hospital policy, ambiguous individual-patient scenarios, prompt injection inside a document, a request for another profile, old-version content in conversation history, adverse-event intake, a PubMed correction, and a new PDF that removes prior guidance. See the full [acceptance matrix](requirements.md).

The initial build has no measured improvement over the baseline, no clinical reviewer scores and no validated zero-hallucination guarantee. The evaluation runner and finite automated checks provide the means to measure these claims honestly.
