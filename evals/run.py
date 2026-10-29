"""Reproducible baseline comparisons. Requires a configured model; never fabricates scores."""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from camzyos.engine import ask
from camzyos.profiles import load_profiles
from camzyos.retrieval import require_index
from camzyos.settings import settings
from camzyos.store import Store

QUESTIONS = ["What is CAMZYOS approved for in Germany?",
             "What should I know about CAMZYOS initiation?",
             "What monitoring information is relevant to my practice?",
             "Summarise the main safety information for CAMZYOS.",
             "What clinical evidence supports the approved use?"]


async def faithfulness(cfg, record):
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.metrics.collections import Faithfulness
    llm = llm_factory(cfg["model"], client=AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"]))
    score = await Faithfulness(llm=llm).ascore(user_input=record["question"],
            response=record["result"]["clinical_response"],
            retrieved_contexts=record["result"]["retrieved_contexts"])
    return score.value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ragas", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", default="reports/comparison.jsonl")
    args = parser.parse_args()
    cfg = settings()
    if not cfg["api_key"]:
        parser.error("Add OPENAI_API_KEY to .env. Live comparisons cannot run without it.")
    tables = load_profiles(cfg["workbook"])
    store = Store(cfg["data_dir"])
    require_index(cfg, store.chunks())
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    cases = [(p, q) for p in tables["HCP_Profile"] for q in QUESTIONS]
    if args.limit:
        cases = cases[:args.limit]
    snapshot = sorted({c["version_id"] for c in store.chunks()})
    with path.open("w", encoding="utf-8") as output:
        for hcp, question in cases:
            for mode in ("generic", "documents", "contextual"):
                if sorted({c["version_id"] for c in store.chunks()}) != snapshot:
                    raise RuntimeError("Corpus changed during evaluation; restart with a fixed snapshot.")
                result = ask(cfg, store, tables, hcp["email"], question, persist=False, search=False, mode=mode)
                record = {"hcp_id": hcp["hcp_id"], "question": question, "mode": mode, "model": cfg["model"],
                          "time": datetime.now(timezone.utc).isoformat(), "source_versions": snapshot,
                          "result": result, "faithfulness": None}
                if args.ragas and result["decision"] == "answer":
                    record["faithfulness"] = asyncio.run(faithfulness(cfg, record))
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()
                print(hcp["hcp_id"], mode, result["decision"], record["faithfulness"])


if __name__ == "__main__":
    main()

