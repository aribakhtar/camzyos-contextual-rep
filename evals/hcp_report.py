"""Create an offline, escaped HTML/CSV review of a completed HCP behavioral run."""
import argparse
import csv
import html
import json
from collections import Counter
from pathlib import Path


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def escaped(value):
    return html.escape(str(value), quote=True)


def pre(value):
    if not isinstance(value, str):
        value = json.dumps(value, indent=2, ensure_ascii=False)
    return "<pre>" + escaped(value) + "</pre>"


def excel_cell(value):
    value = str(value)
    return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value


def render(folder):
    records = {r["case_id"]: r for r in read_lines(folder / "responses.jsonl")}
    scores = {r["case_id"]: r for r in read_lines(folder / "scores.jsonl")} if (folder / "scores.jsonl").exists() else {}
    original = json.loads((folder / "input-original.json").read_text(encoding="utf-8-sig"))
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((folder / "run-metadata.json").read_text(encoding="utf-8"))
    context_path = folder / "contextualization.jsonl"
    context_scores = {r["case_id"]: r for r in read_lines(context_path)} if context_path.exists() else {}
    context_recovery = folder / "contextualization-recovered.jsonl"
    if context_recovery.exists():
        context_scores.update({r["case_id"]: r for r in read_lines(context_recovery)})
    retry_path = folder / "faithfulness-retries.jsonl"
    retries = {r["case_id"]: r for r in read_lines(retry_path)} if retry_path.exists() else {}
    heading = "HCP challenge set: first-run review"
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>' + heading + '</title><style>',
        'body{font:16px/1.5 system-ui,sans-serif;max-width:1200px;margin:30px auto;padding:0 20px;color:#182535;background:#f6f8fa}',
        'h1,h2{line-height:1.2}table{border-collapse:collapse;width:100%;background:white}',
        'td,th{padding:8px;border:1px solid #cdd5df;text-align:left;vertical-align:top}',
        'pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.5 system-ui;background:#f1f4f7;padding:14px;border-radius:6px}',
        'article{background:white;border:1px solid #cdd5df;border-radius:8px;padding:20px;margin:16px 0}',
        'summary{cursor:pointer;font-weight:600;padding:8px}input{font:inherit;padding:10px;width:95%;margin:12px 0}',
        '.note{padding:15px;border-left:4px solid #365e8a;background:#eaf0f8}a{color:#174c91}',
        '</style><h1>' + heading + '</h1>',
        '<p>Run: ' + escaped(folder.name) + ' | Model: ' + escaped(metadata['configuration']['model']) + '</p>',
        '<p class="note">These are automated behavioral judgments, using the same model as the chatbot. '
        'They need human review. Workbook references are synthetic and are not clinical gold. '
        'RAGAS faithfulness scores clinical claims only; handoffs have no faithfulness score. '
        'Context precision/recall are unavailable without reviewed clinical references. '
        'Raw decision equality is not a pass rate: partial_answer is not a native result, and clarify '
        'has limited implementation.</p>',
        '<p>Inputs unchanged: ' + escaped(summary['frozen_inputs_unchanged']) +
        '; HCP memory unchanged: ' + escaped(summary['memory_unchanged']) + '.</p>',
        pre({k: v for k, v in summary.items() if k != "groups"}),
        '<p><a href="findings.md">Reviewed findings and limitations</a> | <a href="results.csv">Download comparison CSV</a> | <a href="responses.jsonl">Raw responses and traces</a>'
        ' | <a href="scores.jsonl">Automated judgments</a> | <a href="reference-audit.json">Reference audit</a></p>',
        '<label for="search">Filter case details by case ID, HCP, category, question or output</label>'
        '<input id="search" type="search" placeholder="For example: negation, weber_001, pharmacovigilance">',
        '<table><thead><tr><th>Case</th><th>Category</th><th>Expected / actual</th>'
        '<th>Behavior alignment</th><th>Faithfulness</th><th>Context usefulness (0–3)</th>'
        '<th>Language / style</th></tr></thead><tbody>']
    context_summary = folder / "contextualization-summary.json"
    if (folder / "contextualization-recovery-summary.json").exists():
        context_summary = folder / "contextualization-recovery-summary.json"
    if context_summary.exists():
        measured = json.loads(context_summary.read_text(encoding="utf-8"))
        parts.insert(-3, '<h2>HCP contextualization — separate automated rubric</h2>'
            '<p class="note">These measures compare actual outputs with own-HCP context and actual turns; '
            'the scorer does not receive the author\'s expected behavior. They remain same-model judgments, '
            'not validated human scores. N/A, uncertain and failed judgments are excluded from relevant '
            'denominators and reported separately. A name-only greeting is not meaningful personalization.</p>'
            + pre({k: v for k, v in measured.items() if k != "groups"})
            + '<p><a href="contextualization.jsonl">Per-case assessments and source context</a> | '
            '<a href="contextualization-summary.json">Grouped metrics</a></p>')
        if (folder / "context-checks-summary.json").exists():
            parts.insert(-3, '<p class="note"><strong>Calibration failed on reviewed examples:</strong> '
                'the subjective judge misidentified English as German and penalized correct patient '
                'handoffs. Do not treat its contextualization scores as validated quality metrics. '
                '<a href="context-checks-summary.json">Separate text/trace checks</a> and '
                '<a href="../findings.md">reviewed findings</a> explain the disagreement.</p>')
        if context_recovery.exists():
            parts.insert(-3, '<p class="note">Single-turn follow-up applicability was corrected deterministically '
                'to N/A on saved assessments, without new model calls. Other observations still pass the same '
                'quote and source validation. Original failed assessments remain unchanged. '
                '<a href="contextualization-recovery-summary.json">Recovery details and effective metrics</a>.</p>')
    recovery_path = folder / "faithfulness-recovery-summary.json"
    if recovery_path.exists():
        parts.insert(-3, '<h2>Failed-metric recovery (initial errors preserved)</h2>' +
            pre(json.loads(recovery_path.read_text(encoding="utf-8"))))
    csv_rows = []
    articles = []
    for case in original:
        rid = case["id"]
        record = records.get(rid, {})
        result = record.get("result", {})
        score = scores.get(rid, {})
        judgment = score.get("behavior") or {}
        metric = score.get("faithfulness", {})
        alignment = judgment.get("expectation_alignment", "not scored")
        actual = result.get("decision", "execution error")
        value = metric.get("value")
        shown_score = "N/A" if value is None else f"{value:.3f}"
        retry = retries.get(rid)
        context_score = context_scores.get(rid, {})
        assessment = context_score.get("assessment", {})
        level = assessment.get("personalization_level") if assessment.get("personalization_applicable") else None
        language = assessment.get("language", {}).get("verdict", "not scored")
        style = assessment.get("style", {}).get("verdict", "not scored")
        if retry and retry.get("status") == "scored":
            shown_score += f"; retry {retry['value']:.3f}"
        issue_counts = Counter(i["kind"] for i in judgment.get("issues", []))
        parts.append('<tr><td><a href="#' + escaped(rid) + '">' + escaped(rid) + '</a></td><td>' +
            escaped(case['category']) + '</td><td>' + escaped(case['expected_decision'] + ' / ' + actual) +
            '</td><td>' + escaped(alignment) + '</td><td>' + shown_score + '</td><td>'
            + escaped(level if level is not None else "N/A") + '</td><td>'
            + escaped(language + ' / ' + style) + '</td></tr>')
        articles.extend(['<article id="' + escaped(rid) + '"><h2>' + escaped(rid + ' — ' + case['hcp_name']) + '</h2>',
            '<p>' + escaped(case['category']) + ' | Expected: ' + escaped(case['expected_decision']) +
            ' | Actual: ' + escaped(actual) + ' | Behavioral judgment: ' + escaped(alignment) + '</p>',
            '<h3>Question</h3>', pre(case['question']), '<h3>Expected behavior (author-provided)</h3>',
            pre(case['expected_behavior']), '<h3>Actual response</h3>', pre(result.get('answer', record.get('error', 'Missing response'))),
            '<h3>Limitations and handoff</h3>', pre({'limitations': result.get('limitations', []), 'handoff': result.get('handoff')}),
            '<h3>Automated assessment (first attempt)</h3>', pre(score),
            '<h3>Contextualization assessment (independent of author expectations)</h3>', pre(context_score),
            '<h3>Metric retry, if any</h3>' + pre(retry) if retry else '',
            '<h3>Citations</h3>', pre(result.get('citations', [])),
            '<details><summary>Ranked retrieved evidence and query</summary>',
            pre({'query': result.get('retrieval_query'), 'evidence': result.get('retrieved_evidence', [])}), '</details>',
            '<details><summary>Context actually used</summary>', pre(result.get('context_used', {})), '</details>',
            '<details><summary>Source-reference audit</summary>', pre(record.get('audit', {})), '</details>',
            '<details><summary>Full raw case, conversation and model-stage trace</summary>', pre(record), '</details>', '</article>'])
        csv_rows.append({'case_id': rid, 'hcp': case['hcp_name'], 'category': case['category'],
            'question': case['question'], 'expected_decision': case['expected_decision'], 'actual_decision': actual,
            'expected_behavior': case['expected_behavior'], 'actual_answer': result.get('answer', ''),
            'behavior_alignment': alignment, 'semantic_decision': judgment.get('semantic_decision', ''),
            'policy_judge': judgment.get('policy_status', ''), 'judge_issues': json.dumps(issue_counts),
            'judge_rationale': judgment.get('rationale', ''), 'faithfulness': '' if value is None else value,
            'faithfulness_status': metric.get('status', 'not requested'),
            'faithfulness_retry': retry.get('value', '') if retry else '',
            'faithfulness_retry_status': retry.get('status', '') if retry else '',
            'citation_ids': '; '.join(c['id'] for c in result.get('citations', [])),
            'handoff_destination': (result.get('handoff') or {}).get('destination', ''),
            'execution_error': record.get('error', ''), 'judge_errors': json.dumps(score.get('errors', {}))})
        csv_rows[-1].update(context_score_status=context_score.get("status", "not requested"),
            personalization_level="" if level is None else level, language=language, style=style,
            conversation_followup=assessment.get("conversation_followup", {}).get("verdict", "not scored"),
            temporal_accuracy=assessment.get("temporal_accuracy", {}).get("verdict", "not scored"))
    parts.extend(['</tbody></table>', *articles,
        '<script>document.getElementById("search").addEventListener("input",function(){'
        'const q=this.value.toLowerCase();document.querySelectorAll("article").forEach(a=>{'
        'a.hidden=!a.textContent.toLowerCase().includes(q)});});</script></html>'])
    (folder / "review.html").write_text("\n".join(parts), encoding="utf-8")
    with (folder / "results.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows({k: excel_cell(v) for k, v in row.items()} for row in csv_rows)
    print(folder / "review.html")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    render(parser.parse_args().run_directory)
