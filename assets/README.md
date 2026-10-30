# Committed prototype inputs

These files are included in Git so a fresh clone has the same inputs.

| Path | Contents |
|---|---|
| [hcp_context.xlsx](hcp_context.xlsx) | Exact byte-for-byte copy of the supplied `Copy of BMS_ContextualAIRep_Hackathon_Dataset_28th Oct 1.xlsx`; 13 tabs, eight synthetic HCPs. |
| [product_information/](product_information/) | All seven original CAMZYOS PDFs, with their original filenames, plus the downloaded German Fachinformation. |
| [manifest.json](manifest.json) | Original filename, origin, SHA-256 and size of each included file. |
| [demo_review.json](demo_review.json) | Exact reviewed EMA source version and review note used to reproduce the prototype's initial active corpus. |

`python -m camzyos.cli prepare` reads these inputs, rebuilds generated `data/` and activates only the exact reviewed EMA version. A changed PDF or extraction configuration does not inherit that review. US documents, historical documents, public overview and the unreviewed German extraction remain outside active answer retrieval.

`python -m camzyos.cli index-all` additionally indexes every PDF's extracted page text in an isolated inspection corpus. This includes all eight documents without changing their clinical review/activation status. [All-PDF testing instructions](../docs/all-pdf-testing.md).

The workbook is read directly by `camzyos/profiles.py`. `HCP_Profile` resolves email and supplies preferences, experience, topics and received-content history. `Personality` and `HCP_Interactions` are filtered to that HCP. `Evidence_Gaps` feeds the answer workflow's review flags. The Graphiti `seed` command imports the same scoped profile/personality/interaction context.

The other sheets remain in the original workbook. The guardrail/question-type sheets informed the implemented rules and evaluation plan; they are not executable instructions. Placeholder clinical chunks, publication abstracts, local-market text and synthetic updates are not imported as real medical evidence. Reading all tabs does not mean every tab is used as a runtime evidence source.

Credentials, new chat histories, generated chunks/indexes and runtime downloads are separate ignored files. Supplied/public materials retain their original authorship and licensing.
