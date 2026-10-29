"""Run source-pinned retrieval or answer evaluations; same runner as the Streamlit screen."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from camzyos.evaluation import cases, evaluate
from camzyos.profiles import load_profiles
from camzyos.settings import settings
from camzyos.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ragas", action="store_true", help="Score context precision/recall; adds paid judge calls")
    parser.add_argument("--answers", action="store_true", help="Also generate contextual answers and score faithfulness")
    parser.add_argument("--case", help="One case ID; omit for all bundled cases")
    parser.add_argument("--email", default="anna.weber@example-clinic.de")
    parser.add_argument("--output")
    args = parser.parse_args()
    cfg = settings()
    store = Store(cfg["data_dir"])
    tables = load_profiles(cfg["workbook"])
    selected = [case for case in cases() if not args.case or case["id"] == args.case]
    if not selected:
        parser.error("Unknown case ID")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = Path(args.output) if args.output else Path("reports") / f"retrieval-{stamp}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = False
    with path.open("w", encoding="utf-8") as output:
        for case in selected:
            record = evaluate(cfg, store, tables, args.email, case, ragas=args.ragas, retrieval_only=not args.answers)
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()
            failed |= bool(record["metric_errors"]) or record["result"]["decision"] in {"setup", "error"}
            print(json.dumps({"case": case["id"], "decision": record["result"]["decision"],
                              "metrics": record["metrics"], "errors": record["metric_errors"]}), flush=True)
    print("Report:", path)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
