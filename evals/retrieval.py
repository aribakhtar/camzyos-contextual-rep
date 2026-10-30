"""Run source-pinned retrieval or answer evaluations; same runner as the Streamlit screen."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from camzyos.evaluation import evaluate, load_cases
from camzyos.profiles import load_profiles
from camzyos.settings import ROOT, settings
from camzyos.store import Store


def positive_integer(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer") from None
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ragas", action="store_true", help="Score context precision/recall; adds paid judge calls")
    parser.add_argument("--answers", action="store_true", help="Generate contextual answers; --ragas also scores faithfulness")
    parser.add_argument("--cases-file", type=Path, metavar="PATH", default=ROOT / "evals/cases.json",
                        help="Source-pinned JSON cases; default: bundled four cases")
    parser.add_argument("--repeats", type=positive_integer, default=1,
                        help="Runs per case (default: 1); reports retain each run with a 1-based repeat_index")
    parser.add_argument("--case", help="One case ID from the chosen cases file; omit for all cases")
    parser.add_argument("--email", default="anna.weber@example-clinic.de")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        loaded, cases_sha256 = load_cases(args.cases_file)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        parser.error(f"Cannot load cases file ({type(exc).__name__})")
    except ValueError as exc:
        parser.error(str(exc))
    selected = [case for case in loaded if not args.case or case["id"] == args.case]
    if not selected:
        parser.error("Unknown case ID")
    cfg = settings()
    store = Store(cfg["data_dir"])
    tables = load_profiles(cfg["workbook"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = Path(args.output) if args.output else Path("reports") / f"retrieval-{stamp}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = False
    with path.open("w", encoding="utf-8") as output:
        for repeat_index in range(1, args.repeats + 1):
            for case in selected:
                record = evaluate(cfg, store, tables, args.email, case, ragas=args.ragas, retrieval_only=not args.answers)
                record.update(repeat_index=repeat_index, repeats=args.repeats,
                              cases_file=str(args.cases_file.resolve()), cases_file_sha256=cases_sha256)
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()
                failed |= not record["successful"]
                print(json.dumps({"case": case["id"], "repeat_index": repeat_index,
                                  "decision": record["result"]["decision"], "successful": record["successful"],
                                  "metrics": record["metrics"], "errors": record["metric_errors"]}), flush=True)
    print("Report:", path)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
