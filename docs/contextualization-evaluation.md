# Measuring HCP contextualization separately from RAG

AI-authored expected answers are unreviewed hypotheses. Keep them for comparison, but do not treat
them as clinical evidence or use a literal decision match as the main quality score.

The full evaluation uses three separate views:

1. **Behavioral expectation alignment:** the existing judge compares the output with the supplied
   expectation and flags limitations. This is useful for annotation review, not an authoritative pass rate.
2. **HCP contextualization:** `evals/contextualization.py` compares saved actual responses with own-HCP
   workbook context, memory actually supplied to generation, and actual conversation turns. It does
   not receive `expected_behavior`, `expected_decision`, or the scripted assistant placeholder.
3. **RAG grounding:** RAGAS faithfulness scores generated clinical claim text against retrieved eligible
   passages. Reference-based context precision/recall are measured separately using source-pinned
   questions with verified excerpt/ID matches. The 132-case behavioral file lacks those references.

## HCP measures

| Measure | Calculation | Interpretation |
|---|---|---|
| Personal fact support | Supported / (supported + unsupported + contradicted personal claims) | Report uncertain claims separately; no claims means N/A, not 1.0. |
| Substantive personal fact support | Same calculation, excluding identity/name claims | Prevents correct greetings from dominating grounding. |
| Useful personalization | Mean 0–3 on cases where personalization is applicable | 0: none; 1: superficial; 2: relevant adaptation; 3: correct, specifically useful adaptation. |
| Language compliance | Matching detected answer language / assessable language requirements | Target comes from an explicit request when recognized, otherwise the HCP profile. |
| Style compliance | Met / (met + not met) | Explicit style request first, then applicable profile style. |
| Conversation follow-up | Met / (met + not met) on applicable actual multi-turn cases | Does not assume the author's scripted assistant reply occurred. |
| Temporal accuracy | Met / (met + not met) on dated/status claims or requests | Old pending status is not proof it remains pending today. |
| Isolation observations | No disclosure observed / assessable outputs | A finite observed result, not a guarantee that leakage is impossible. |

Every measure records its denominator, not-applicable/uncertain counts, and scoring failures.
Per-HCP, category and actual-decision groups are saved. A correct fact-support score can coexist with
poor usefulness: a chatbot that says almost nothing may make few factual errors. Inspect answer
coverage and handoffs alongside the scores.

## Validation and limitations

These contextualization measures are a new automated rubric using the same configured model as the
chatbot. They have not been calibrated against independent human labels. The scorer preserves exact
quotes, reasons, and source IDs for review. Output schemas restrict source IDs to supplied context.
Quotes must occur in the actual answer after whitespace/case normalization; failed validation is
recorded with the rejected assessment, excluded from averages, and not silently regenerated.

When the sole validation failure is a judge assigning a follow-up score to a verified single-turn
case, `evals/contextualization_recovery.py` can deterministically mark that criterion N/A. It then
rechecks every quote/source constraint, preserves the original failed row, and writes separate
recovery records and effective aggregates. It makes no model calls and does not recover fabricated
quotes or change any personal-fact judgment. Initial error counts remain reported.

The model detects the main answer language; Python applies the known target-language rule. The
explicit-request parser recognizes common English/German phrases, not arbitrary or negated language
instructions. Inspect `language_policy` and the original question where phrasing is ambiguous.
The original judge language verdict is retained beside the applied rule.

The full-run spot check also found the judge misidentifying English text as German and penalizing
correct patient handoffs as failures to retain conversation context. Its subjective scores are
therefore **not calibrated acceptance metrics**. The raw scores remain diagnostic artifacts.

`evals/context_checks.py` performs separate checks on all saved outputs: exact known English handoff
templates, otherwise seeded text-only language identification; declared HCP-key scope; citation
membership; and actual earlier user messages in classifier payloads. It makes no model calls. The
language detector uses a 0.90 top-score threshold and abstains on very short/uncertain text; these
scores are not calibrated correctness probabilities. See the [langdetect documentation](https://github.com/Mimino666/langdetect).
Trace presence is not a semantic understanding score, and declared IDs do not prove factual support.

Pilot checks found evaluator errors: a generic referral was treated as a personal action claim, and
an English answer was marked compliant despite a German profile preference. The rubric and language
calculation were revised before full scoring. Pilot artifacts remain separate. These fixes do not
establish that the remaining model judgments are correct. Reviewer attention is still needed for
personalization applicability, semantic support, temporal assumptions and policy routes.

RAGAS faithfulness does not assess the entire personal introduction, route correctness, or clinical
completeness. A well-supported answer can still violate a mandatory handoff rule. Missing reference
metrics are N/A; placeholder workbook material is never converted into gold clinical evidence.

## Commands

First run the full behavioral set, keeping its original input bytes and application outputs:

```powershell
.\.venv\Scripts\python.exe -m evals.hcp --cases-file 'C:\path\hcp-cases.json' --judge-behavior --ragas --workers 3
```

Then score the saved responses and rebuild their review page:

```powershell
.\.venv\Scripts\python.exe -m evals.contextualization --run-dir 'reports\hcp-golden-TIMESTAMP' --workers 3
# Optional deterministic recovery after the full scoring file is complete:
.\.venv\Scripts\python.exe -m evals.contextualization_recovery --run-dir 'reports\hcp-golden-TIMESTAMP'
.\.venv\Scripts\python.exe -m evals.context_checks --run-dir 'reports\hcp-golden-TIMESTAMP'
.\.venv\Scripts\python.exe -m evals.hcp_report 'reports\hcp-golden-TIMESTAMP'
```

The context scorer requires a completed, hash-matching response file and the unchanged workbook.
It refuses to overwrite an existing `contextualization.jsonl`. It makes paid judge calls but never
reruns the chatbot, changes source eligibility, or writes HCP conversation memory.

For source-pinned RAG checks with repeated measurements:

```powershell
.\.venv\Scripts\python.exe -m evals.retrieval --ragas --repeats 3
.\.venv\Scripts\python.exe -m evals.retrieval --ragas --answers --repeats 3
```

Four questions repeated three times remain four distinct development questions. Repetition measures
variability; it does not establish generalization. Keep source/configuration snapshots, failures and
all repetitions. Review or replace disputed annotations before creating a separately authored
held-out set. Do not tune the chatbot while a benchmark is running.
