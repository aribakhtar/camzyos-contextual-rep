# CAMZYOS evaluation metrics

30 October 2026 — recorded benchmark means, before the latest fixes.

| Evaluation | Context precision | Context recall | Faithfulness | Mean reciprocal rank |
|---|---:|---:|---:|---:|
| Retrieval only | 0.964 | 1.000 | — | 1.000 |
| Contextual answers | 0.897 | 1.000 | 0.903 | 0.917 |
| HCP scenarios: generated clinical answers | — | — | 0.911 | — |

| HCP context metric | Value |
|---|---:|
| Own-HCP context declaration among generated answers | 100% |
| German-language alignment | 10.6% |
| Overall personalization score | Not validated |

— = not measured or not applicable. Context declaration measures trace usage, not personalization quality.

[Recorded results](evaluation-results.json) · [Method and limitations](evaluation.md)
