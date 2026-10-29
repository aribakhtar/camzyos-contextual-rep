import argparse
import json

from camzyos import graph
from camzyos.ingest import build, fetch_public, prepare_demo, process_document, publish_version
from camzyos.profiles import context, load_profiles
from camzyos.settings import settings, sources
from camzyos.store import Store


def main():
    parser = argparse.ArgumentParser(description="CAMZYOS prototype operations")
    parser.add_argument("command", choices=["build", "prepare", "ingest", "sources", "activate",
                                            "fetch", "sync", "seed", "doctor"])
    parser.add_argument("--source")
    parser.add_argument("--version")
    parser.add_argument("--note", default="")
    parser.add_argument("--file", help="Replacement PDF path for --source; parsed and indexed before review")
    args = parser.parse_args()
    if args.file and (not args.source or args.command != "ingest"):
        parser.error("--file requires ingest --source SOURCE_ID")
    if args.command == "activate" and not args.version:
        parser.error("activate requires --version VERSION_ID and --note REVIEW_NOTE")
    cfg = settings()
    store = Store(cfg["data_dir"])
    catalog = sources(cfg)
    store.register(catalog)
    selected = [s for s in catalog if not args.source or s["id"] == args.source]
    if args.source and not selected:
        parser.error("Unknown source ID")
    if args.command == "build":
        print(json.dumps(build(cfg, store, catalog), indent=2))
    elif args.command == "prepare":
        for result in prepare_demo(cfg, store, catalog):
            print(json.dumps(result, ensure_ascii=True))
        tables = load_profiles(cfg["workbook"])
        print(json.dumps({"hcp_profiles": len(tables["HCP_Profile"]),
                          "past_interactions": len(tables["HCP_Interactions"]),
                          "active_chunks": len(store.chunks())}))
    elif args.command in {"ingest", "fetch"}:
        failed = False
        for source in selected:
            try:
                path = fetch_public(cfg, source) if args.command == "fetch" else args.file
                print(json.dumps(process_document(cfg, store, source, path), ensure_ascii=True))
            except Exception as exc:
                failed = True
                print(json.dumps({"source": source["id"], "error": type(exc).__name__, "message": str(exc)}))
        if failed:
            raise SystemExit(1)
    elif args.command == "activate":
        publish_version(cfg, store, args.version, args.note)
        print("Activated", args.version)
    elif args.command == "sources":
        for v in store.versions():
            print(v["id"], v["status"], v["source"]["title"])
    elif args.command == "sync":
        if not cfg["api_key"]:
            parser.error("Set OPENAI_API_KEY before embedding documents.")
        print("Indexed eligible chunks:", graph.sync_documents(cfg, store))
    elif args.command == "seed":
        if not cfg["api_key"]:
            parser.error("Set OPENAI_API_KEY before seeding Graphiti.")
        tables = load_profiles(cfg["workbook"])
        for hcp in tables["HCP_Profile"]:
            # Existing synthetic dataset is deliberately imported; no new user conversation here.
            print(hcp["hcp_id"], graph.retain(cfg, hcp["hcp_id"], context(tables, hcp), consent=True, seed=True))
    else:
        print(json.dumps({"workbook_found": cfg["workbook"].exists(), "pdf_folder_found": cfg["pdf_dir"].exists(),
                          "api_key_configured": bool(cfg["api_key"]), "neo4j_connected": graph.status(cfg),
                          "active_chunks": len(store.chunks()),
                          "retrieval_index": graph.index_status(cfg, store.chunks(all_accounts=True))}, indent=2))


if __name__ == "__main__":
    main()

