"""Recover only deterministic single-turn applicability errors; no model calls or answer regeneration."""
import argparse
import copy
import json
from pathlib import Path

from camzyos.profiles import load_profiles
from camzyos.settings import settings
from evals.contextualization import Assessment, payload_for, summarize, validate_assessment
from evals.hcp import sha, write_json
from evals.hcp_report import read_lines

APPLICABILITY_ERROR = "Single-turn answer cannot establish conversation retention."


def recover(row, record, tables):
    if row.get("status") != "error" or row.get("validation_error") != APPLICABILITY_ERROR:
        return None
    payload = payload_for(tables, record)
    if len(payload["actual_turns"]) != 1:
        raise ValueError("Only a verified single-turn record can receive this recovery.")
    candidate = Assessment.model_validate(row["unvalidated_assessment"])
    prior = candidate.conversation_followup.model_dump()
    candidate.conversation_followup.verdict = "not_applicable"
    candidate.conversation_followup.rationale = "Exactly one actual user turn; conversation-followup quality is not assessable."
    candidate.conversation_followup.output_quotes = []
    validate_assessment(candidate, payload)  # All quote, source and support checks still apply.
    measured = candidate.model_dump()
    measured["language_judge_original"] = copy.deepcopy(measured["language"])
    target, detected = payload["language_policy"]["target"], measured["response_language"]
    verdict = "uncertain" if target is None or detected == "uncertain" else "met" if target == detected else "not_met"
    measured["language"].update(verdict=verdict,
        rationale=f"Required: {target} ({payload['language_policy']['basis']}); detected main-answer language: {detected}.")
    return {**row, "status": "scored", "assessment": measured, "source_context": payload["sources"],
        "language_policy": payload["language_policy"], "recovery": {
            "kind": "deterministic_single_turn_not_applicable", "original_status": row["status"],
            "original_followup_judgment": prior, "new_model_calls": 0,
            "note": "Original failed assessment retained; no factual judgment or chatbot answer regenerated."}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    folder = args.run_dir
    cfg = settings()
    metadata = json.loads((folder / "run-metadata.json").read_text(encoding="utf-8"))
    initial_summary = json.loads((folder / "contextualization-summary.json").read_text(encoding="utf-8"))
    original = (folder / "contextualization.jsonl").read_bytes()
    if sha((folder / "responses.jsonl").read_bytes()) != metadata["responses_sha256"]:
        parser.error("Response file changed.")
    if sha(cfg["workbook"].read_bytes()) != metadata["frozen_inputs"]["workbook"]:
        parser.error("Workbook changed.")
    rows = read_lines(folder / "contextualization.jsonl")
    if len(rows) != initial_summary["cases"] or len(rows) != metadata["cases"]:
        parser.error("Scoring is incomplete.")
    records = {r["case_id"]: r for r in read_lines(folder / "responses.jsonl")}
    tables = load_profiles(cfg["workbook"])
    recovered = {}
    with (folder / "contextualization-recovered.jsonl").open("x", encoding="utf-8") as output:
        for row in rows:
            fixed = recover(row, records[row["case_id"]], tables)
            if fixed:
                recovered[row["case_id"]] = fixed
                output.write(json.dumps(fixed, ensure_ascii=False, default=str) + "\n")
    effective = [recovered.get(r["case_id"], r) for r in rows]
    summary = summarize(effective)
    summary["groups"] = {field: {value: summarize([r for r in effective if r[field] == value])
        for value in sorted({r[field] for r in effective})} for field in ("hcp_id", "category", "decision")}
    summary.update(recovered_applicability_cases=len(recovered), initial_statuses=initial_summary["statuses"],
        original_scores_sha256=sha(original), recovery_code_sha256=sha(Path(__file__).read_bytes()),
        original_scores_unchanged=sha((folder / "contextualization.jsonl").read_bytes()) == sha(original),
        responses_unchanged=sha((folder / "responses.jsonl").read_bytes()) == metadata["responses_sha256"],
        additional_model_calls=0)
    write_json(folder / "contextualization-recovery-summary.json", summary)
    print(json.dumps({"recovered": len(recovered), "statuses": summary["statuses"]}))


if __name__ == "__main__":
    main()
