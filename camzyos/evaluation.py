"""Source-pinned retrieval tests and RAGAS scoring; never write HCP conversation memory."""
import asyncio
import json
import math
from datetime import datetime, timezone

from camzyos.engine import ask
from camzyos.profiles import resolve_hcp
from camzyos.retrieval import retrieve
from camzyos.settings import ROOT


def cases():
    return json.loads((ROOT / "evals/cases.json").read_text(encoding="utf-8"))


def reference_valid(case, chunks):
    expected = {c["id"]: c for c in chunks}
    ids = case["reference_ids"]
    return bool(ids) and all(cid in expected for cid in ids) and any(
        " ".join(case["reference"].split()) in " ".join(expected[cid]["text"].split()) for cid in ids)


def retrieval_metrics(retrieved, expected):
    ids = [e["id"] for e in retrieved]
    hits = set(ids).intersection(expected)
    rank = next((i for i, cid in enumerate(ids, 1) if cid in expected), None)
    return {"reference_hit_at_k": float(bool(hits)),
            "reference_recall_at_k": len(hits) / len(set(expected)) if expected else None,
            "reciprocal_rank": 1 / rank if rank else 0.0, "retrieved_count": len(ids)}


async def score_ragas(cfg, question, reference, result):
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.metrics.collections import ContextPrecision, ContextRecall, Faithfulness

    texts = [e["text"] for e in result.get("retrieved_evidence", [])]
    scores, errors, details = {}, {}, {}
    async with AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=60, max_retries=1) as client:
        judge = llm_factory(cfg["model"], client=client)
        jobs = {"context_precision": (ContextPrecision(llm=judge), {"reference": reference}),
                "context_recall": (ContextRecall(llm=judge), {"reference": reference})}
        if result.get("decision") == "answer":
            jobs["faithfulness"] = (Faithfulness(llm=judge), {"response": result["clinical_response"]})

        async def score(name, metric, extra):
            try:
                value = await asyncio.wait_for(metric.ascore(user_input=question,
                    retrieved_contexts=texts, **extra), timeout=120)
                if not math.isfinite(float(value.value)):
                    raise ValueError("Judge returned an undefined score")
                scores[name] = value.value
                if getattr(value, "reason", None) or getattr(value, "traces", None):
                    details[name] = {"reason": getattr(value, "reason", None),
                                     "traces": getattr(value, "traces", None)}
            except Exception as exc:
                scores[name] = None
                errors[name] = type(exc).__name__
        await asyncio.gather(*(score(name, metric, extra) for name, (metric, extra) in jobs.items()))
    return scores, errors, details


def evaluate(cfg, store, tables, email, case, *, mode="contextual", ragas=False, retrieval_only=False):
    hcp = resolve_hcp(tables, email)
    account = cfg["account_map"].get(hcp["hcp_id"]) if hcp else None
    chunks = store.chunks(account)
    snapshot = sorted(c["id"] for c in chunks)
    valid = reference_valid(case, chunks)
    if retrieval_only:
        evidence, backend, warnings = retrieve(cfg, store, case["question"], account)
        result = {"decision": "retrieval", "answer": "Retrieval-only test; no answer generated.",
                  "retrieved_evidence": evidence, "retrieval_query": case["question"],
                  "retrieval_backend": backend, "citations": [], "context_used": {}, "warnings": warnings}
    else:
        result = ask(cfg, store, tables, email, case["question"], persist=False, search=False, mode=mode)
    if sorted(c["id"] for c in store.chunks(account)) != snapshot:
        raise RuntimeError("Corpus changed during evaluation; rerun against a fixed version.")
    evidence = result.get("retrieved_evidence", [])
    record = {"case_id": case["id"], "question": case["question"], "hcp_id": hcp["hcp_id"] if hcp else None,
              "mode": "retrieval" if retrieval_only else mode, "model": cfg["model"],
              "embedding_model": cfg["embedding_model"], "retrieval_top_k": cfg["retrieval_top_k"],
              "time": datetime.now(timezone.utc).isoformat(), "source_versions": sorted({c["version_id"] for c in chunks}),
              "reference": case, "reference_valid": valid, "result": result,
              "metrics": {}, "metric_errors": {}, "metric_details": {}}
    if mode != "generic" or retrieval_only:
        if valid:
            record["metrics"] = retrieval_metrics(evidence, case["reference_ids"])
        else:
            record["metric_errors"]["reference"] = "Reference is stale or outside the eligible corpus; review it."
        if ragas and valid and evidence:
            scores, errors, details = asyncio.run(score_ragas(cfg, case["question"], case["reference"], result))
            record["metrics"].update(scores)
            record["metric_errors"].update(errors)
            record["metric_details"].update(details)
    return record
