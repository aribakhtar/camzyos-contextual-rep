"""Text-only language and deterministic provenance checks on saved responses; no model calls."""
import argparse
import json
from collections import Counter
from pathlib import Path

from langdetect import DetectorFactory, detect_langs

from camzyos.engine import REASONS
from camzyos.profiles import load_profiles
from camzyos.settings import settings
from evals.contextualization import payload_for
from evals.hcp import sha, write_json
from evals.hcp_report import read_lines

DetectorFactory.seed = 0


def language_of(answer):
    # These exact application templates have been inspected and are English.
    if answer in REASONS.values():
        return {"language": "English", "method": "exact English handoff template", "detector_scores": []}
    if len(answer.split()) < 5:
        return {"language": None, "method": "insufficient text", "detector_scores": []}
    choices = detect_langs(answer)
    first = choices[0]
    language = {"en": "English", "de": "German"}.get(first.lang) if first.prob >= 0.90 else None
    return {"language": language, "method": "langdetect 1.0.9, seed 0, top score >= 0.90",
            "detector_scores": [{"language": item.lang, "score": item.prob} for item in choices]}


def check_case(tables, record):
    payload = payload_for(tables, record)
    result = record["result"]
    detection = language_of(result.get("answer", ""))
    target = payload["language_policy"]["target"]
    language_match = None if target is None or detection["language"] is None else target == detection["language"]
    citations = result.get("citations", [])
    retrieved = {item["id"] for item in result.get("retrieved_evidence", [])}
    keys = list(result.get("context_used", {}))
    foreign = [key for key in keys if key.startswith("HCP_") and not key.startswith(record["hcp_id"] + ".")]
    history = [call["input"].get("conversation", []) for call in record.get("trace", [])
               if call.get("stage") == "Decision"]
    prior = [turn["question"] for turn in record["turns"][:-1]]
    retained = all(any(any(message.get("role") == "user" and message.get("content") == question
                          for message in batch) for batch in history) for question in prior) if prior else None
    return {"case_id": record["case_id"], "hcp_id": record["hcp_id"], "decision": result["decision"],
        "language_target": target, "language_target_basis": payload["language_policy"]["basis"],
        "language_detection": detection, "language_match": language_match,
        "foreign_declared_context_keys": foreign, "declared_context_key_count": len(keys),
        "citation_count": len(citations),
        "citation_membership_pass": all(item["id"] in retrieved for item in citations) if citations else None,
        "actual_prior_user_turns": len(prior), "prior_turns_in_classifier_context": retained,
        "final_policy_route": result.get("policy_route")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    folder = args.run_dir
    cfg = settings()
    metadata = json.loads((folder / "run-metadata.json").read_text(encoding="utf-8"))
    if sha((folder / "responses.jsonl").read_bytes()) != metadata["responses_sha256"]:
        parser.error("Raw responses changed.")
    if sha(cfg["workbook"].read_bytes()) != metadata["frozen_inputs"]["workbook"]:
        parser.error("Workbook changed.")
    rows = [check_case(load_profiles(cfg["workbook"]), r) for r in read_lines(folder / "responses.jsonl")]
    with (folder / "context-checks.jsonl").open("x", encoding="utf-8") as output:
        output.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    language = [r["language_match"] for r in rows if r["language_match"] is not None]
    answers = [r for r in rows if r["decision"] == "answer"]
    followups = [r for r in rows if r["actual_prior_user_turns"]]
    summary = {"cases": len(rows), "new_model_calls": 0,
        "language": {"matches": sum(language), "assessed": len(language), "unassessed": len(rows) - len(language),
            "match_rate": sum(language) / len(language) if language else None,
            "targets": dict(Counter(r["language_target"] for r in rows)),
            "detected": dict(Counter(r["language_detection"]["language"] for r in rows))},
        "answers": len(answers), "answers_with_declared_context": sum(bool(r["declared_context_key_count"]) for r in answers),
        "foreign_declared_context_key_cases": sum(bool(r["foreign_declared_context_keys"]) for r in rows),
        "citation_membership_failures": sum(r["citation_membership_pass"] is False for r in rows),
        "multi_turn": {"cases": len(followups), "prior_history_present": sum(r["prior_turns_in_classifier_context"] for r in followups),
            "final_routes": dict(Counter(r["final_policy_route"] for r in followups))},
        "responses_sha256": metadata["responses_sha256"], "checker_sha256": sha(Path(__file__).read_bytes()),
        "limitations": ["Language identification can fail on short or mixed-language text; inspect disagreements.",
                        "Context-key scope and citation membership do not prove semantic correctness or usefulness.",
                        "History presence and route counts do not prove general conversation understanding."]}
    write_json(folder / "context-checks-summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
