"""Local synthetic-HCP demo. Email selection is not production authentication."""
import hashlib
import json

import streamlit as st

from camzyos import graph, profiles
from camzyos.engine import ask
from camzyos.evaluation import cases, evaluate
from camzyos.ingest import build, fetch_public, process_document, publish_version
from camzyos.settings import settings, sources
from camzyos.store import Store

st.set_page_config(page_title="CAMZYOS Contextual Rep", page_icon="💬", layout="wide")
cfg = settings()
store = Store(cfg["data_dir"])
catalog = sources(cfg)
store.register(catalog)
st.title("CAMZYOS · Contextual Rep")
st.caption("Germany · HCP information · Research prototype with synthetic profiles")
if not cfg["workbook"].exists():
    st.error("Set WORKBOOK_PATH in .env to the supplied workbook. See README for setup.")
    st.stop()
try:
    tables = profiles.load_profiles(cfg["workbook"])
except Exception as exc:
    st.error(f"Workbook could not be loaded ({type(exc).__name__}). Close Excel and retry.")
    st.stop()

with st.sidebar:
    st.subheader("HCP session")
    st.caption("Synthetic demo login only. Deploy only after adding verified authentication.")
    email = st.text_input("HCP email", value="anna.weber@example-clinic.de")
    hcp = profiles.resolve_hcp(tables, email)
    identity = hcp["hcp_id"] if hcp else "unknown:" + email.strip().casefold()
    if st.session_state.get("identity") != identity:
        st.session_state.clear()
        st.session_state.identity = identity
        st.session_state.messages = []
    if hcp:
        st.success(f"Welcome, {hcp['name']}")
        st.caption(f"{hcp.get('specialty')} · {hcp.get('workplace')}")
    else:
        st.info("Email not found. General approved-content mode; no personal history.")
    persist = st.checkbox("Save my new conversations and memory", value=False, disabled=not bool(hcp))
    st.caption("Selected context is sent to your configured model. Storage is a separate opt-in.")
    search = st.toggle("PubMed search", value=cfg["pubmed_enabled"], disabled=not bool(hcp))
    st.caption("Off disables live search; reviewed publications already imported remain available.")
    if hcp and st.button("Forget saved chat memory"):
        store.delete_history(hcp["hcp_id"])
        try:
            graph.forget(cfg, hcp["hcp_id"])
            st.success("Saved chat memory removed. The supplied synthetic profile remains.")
        except Exception:
            st.warning("Local chat memory removed. Graphiti was unreachable; graph deletion is incomplete.")
        st.session_state.messages = []
    page = st.radio("View", ["Chat", "Compare", "Evaluation", "Sources & updates", "Context"])
    active_chunks = store.chunks(cfg['account_map'].get(hcp['hcp_id']) if hcp else None)
    readiness = graph.index_status(cfg, active_chunks)
    if readiness["ready"]:
        st.success(f"Retrieval ready: {readiness['indexed_chunks']}/{len(active_chunks)} passages indexed")
    else:
        st.warning("Retrieval not ready. Complete Sources & updates before asking clinical questions.")
    if not cfg["api_key"]:
        st.warning("API key missing. Add it before document setup or clinical answers.")


def render(result, key):
    if result["decision"] == "baseline":
        st.warning("Unverified baseline — evaluation only")
    st.markdown(result["answer"])
    for warning in result.get("warnings", []):
        st.warning(warning)
    if result.get("retrieval_backend"):
        st.caption(result["retrieval_backend"])
    if result.get("limitations"):
        st.info("\n".join(result["limitations"]))
    if result.get("evidence_gaps"):
        with st.expander("Relevant evidence-gap review flags", expanded=True):
            st.caption("Supplied dataset flags; these do not establish that real-world evidence is absent.")
            st.json(result["evidence_gaps"])
    with st.expander("Sources used", expanded=result["decision"] == "setup"):
        for i, item in enumerate(result.get("citations", []), 1):
            source = item["source"]
            st.markdown(f"**[{i}] {source['title']}**")
            st.caption(f"{item.get('section', '')} · PDF pages {item.get('page')}–{item.get('page_end')} "
                       f"· version {item['version_id']}")
            if source.get("url"):
                st.link_button("Publisher source", source["url"])
            st.text(item["text"])
    with st.expander("Personal context used"):
        st.json(result.get("context_used", {}))
    if result.get("discoveries"):
        with st.expander("PubMed discovery / review queue"):
            st.caption("Discovery does not imply approval. Full text has not been accessed.")
            for record in result["discoveries"]:
                st.markdown(f"[{record['title']}]({record['url']}) — PMID {record['pmid']}")
                st.caption("Eligible only if reviewed in config.yaml; corrections/retractions are checked.")
    if result.get("handoff"):
        with st.expander("Handoff summary — review before sharing", expanded=True):
            st.json(result["handoff"])
            st.download_button("Download summary (does not send)",
                               json.dumps(result["handoff"], ensure_ascii=False, indent=2),
                               file_name="handoff.json", mime="application/json", key=f"handoff-{key}")


if page == "Context":
    st.subheader("Loaded HCP context")
    st.json(profiles.context(tables, hcp))
    st.info("Account policies require explicit HCP-to-account mappings and verified source documents.")
elif page == "Sources & updates":
    st.subheader("Source registry and versioned updates")
    st.warning("Local reviewer tools. Prototype eligibility is not sponsor compliance approval.")
    st.caption("Prepare documents here before chat: parse → chunk → index → review → activate. "
               "Chat never parses or embeds document files.")
    st.json(readiness)
    if st.button("Build bundled document index", disabled=not bool(cfg["api_key"])):
        with st.spinner("Preparing bundled documents and checking the complete index..."):
            try:
                st.session_state.build_status = build(cfg, store, catalog)
                st.rerun()
            except Exception as exc:
                st.error(f"Build incomplete ({type(exc).__name__}). Check configuration and retry.")
    st.dataframe([{k: s.get(k, "") for k in ("id", "title", "market", "audience", "eligible", "contribution")}
                  for s in catalog], hide_index=True)
    selected = st.selectbox("Source", catalog, format_func=lambda s: s["title"])
    uploaded = st.file_uploader("Stage a replacement PDF", type=["pdf"])
    st.caption("Uploading starts parsing, chunking and indexing automatically and may use your model API. "
               "The new version stays hidden from chat until reviewed and activated.")
    retry = st.button("Process / index source", disabled=not bool(cfg["api_key"]))
    upload_id = (selected["id"], hashlib.sha256(uploaded.getvalue()).hexdigest()) if uploaded else None
    new_upload = upload_id and st.session_state.get("processed_upload") != upload_id
    if retry or (new_upload and cfg["api_key"]):
        st.session_state.processed_upload = upload_id
        try:
            path = None
            if uploaded:
                folder = cfg["data_dir"] / "uploads"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / selected["file"]
                path.write_bytes(uploaded.getvalue())
            with st.spinner("Parsing, chunking and indexing the staged version..."):
                st.json(process_document(cfg, store, selected, path))
            st.success("Processing complete. Review the extraction below before activation.")
        except Exception as exc:
            st.error(str(exc))
    if selected.get("url") and st.button("Check publisher for an updated PDF"):
        try:
            st.json(process_document(cfg, store, selected, fetch_public(cfg, selected)))
        except Exception as exc:
            st.error(f"Publisher check failed ({type(exc).__name__}). Existing valid versions remain available.")
    versions = [v for v in store.versions() if v["source_id"] == selected["id"]]
    if versions:
        version = st.selectbox("Version", versions, format_func=lambda v: v["id"] + " · " + v["status"])
        st.json({"hash": version["hash"], "created": version["created"], "note": version["note"],
                 "extraction_audit": version["audit"]})
        review = st.text_input("Review note (scope, version and limitations checked)")
        acknowledged = st.checkbox("I reviewed this source's scope and extraction limitations")
        if st.button("Activate reviewed version", disabled=not acknowledged or not review):
            try:
                publish_version(cfg, store, version["id"], review)
                st.success("Index verified and version activated. Previous versions remain auditable.")
            except Exception as exc:
                st.error(str(exc))
        if st.button("Withdraw this version"):
            store.deactivate(version["id"])
            st.success("Version excluded from new answers.")
    if st.button("Sync active document embeddings to Neo4j", disabled=not bool(cfg["api_key"])):
        with st.spinner("Embedding eligible passages..."):
            try:
                st.success(f"Indexed {graph.sync_documents(cfg, store)} passages.")
            except Exception as exc:
                st.error(f"Index incomplete ({type(exc).__name__}). Chat requires a complete index.")
elif page == "Evaluation":
    st.subheader("Test retrieval and answer quality")
    st.caption("Runs use the selected HCP without saving chat memory. PubMed is disabled. "
               "RAGAS uses paid judge calls; scores do not replace clinical review.")
    case = st.selectbox("Test case", cases(), format_func=lambda c: c["question"])
    with st.expander("Reference and expected source"):
        st.json(case)
    test = st.radio("Test type", ["Retrieval only", "Contextual answer"], horizontal=True)
    use_ragas = st.checkbox("Score with RAGAS", value=True)
    st.caption("Reference hit/recall and reciprocal rank locate the expected passage. RAGAS context precision "
               "and recall assess retrieval; faithfulness is added when an answer is generated.")
    if st.button("Run evaluation", disabled=not readiness["ready"] or not bool(cfg["api_key"])):
        st.session_state.pop("evaluation", None)
        with st.spinner("Running the selected test..."):
            try:
                st.session_state.evaluation = evaluate(cfg, store, tables, email, case,
                    ragas=use_ragas, retrieval_only=test == "Retrieval only")
            except Exception as exc:
                st.error(f"Evaluation could not finish ({type(exc).__name__}). Check setup and retry.")
    if record := st.session_state.get("evaluation"):
        st.write(record["question"])
        st.caption(f"Result: {record['result']['decision']} · {record['mode']}")
        st.caption("Search query used: " + record["result"].get("retrieval_query", record["question"]))
        st.dataframe([{"metric": k, "value": v} for k, v in record["metrics"].items()], hide_index=True)
        if record["metric_errors"]:
            st.warning("Some scores are unavailable; missing scores are not passes.")
            st.json(record["metric_errors"])
        if record.get("metric_details"):
            with st.expander("RAGAS judge details"):
                st.json(record["metric_details"])
        if record["mode"] != "retrieval":
            render(record["result"], "evaluation")
        st.caption("Retrieved passages in rank order")
        for rank, passage in enumerate(record["result"].get("retrieved_evidence", []), 1):
            with st.expander(f"{rank}. {passage['source']['title']} · pages "
                             f"{passage.get('page')}–{passage.get('page_end')}"):
                st.caption(passage["id"])
                st.text(passage["text"])
        st.download_button("Download evaluation JSON", json.dumps(record, ensure_ascii=False, indent=2),
                           file_name="evaluation.json", mime="application/json")
elif page == "Compare":
    st.subheader("Same question · same model · three context settings")
    st.caption("Runs do not save memory. Compare actual results, including ties and failures.")
    query = st.text_area("Evaluation question", "What should I know about CAMZYOS monitoring?")
    if st.button("Run comparison", disabled=not bool(cfg["api_key"]) or not readiness["ready"]):
        for column, mode in zip(st.columns(3), ["generic", "documents", "contextual"]):
            with column, st.spinner(mode):
                st.subheader(mode.title())
                result = ask(cfg, store, tables, email, query, persist=False, search=False, mode=mode)
                render(result, mode)
else:
    if not st.session_state.messages:
        st.write(f"Hello, {hcp['name']}. What would you like to know about CAMZYOS?" if hcp
                 else "What would you like to know about CAMZYOS in Germany?")
    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            render(message["result"], i) if message["role"] == "assistant" else st.write(message["content"])
    question = st.chat_input("Ask about CAMZYOS")
    if question:
        history = [{"role": m["role"], "content": m.get("content", m.get("result", {}).get("answer", ""))}
                   for m in st.session_state.messages[-8:]]
        if hcp and persist and not history:
            history = store.history(hcp["hcp_id"])
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"), st.spinner("Checking context and evidence..."):
            result = ask(cfg, store, tables, email, question, history, persist, search)
            render(result, len(st.session_state.messages))
        st.session_state.messages.append({"role": "assistant", "result": result})
