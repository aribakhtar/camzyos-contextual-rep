"""Graphiti per-HCP memory plus a separate, authoritative document index in Neo4j."""
import asyncio
import json
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from neo4j import GraphDatabase


def driver(cfg):
    return GraphDatabase.driver(cfg["neo4j_uri"], auth=(cfg["neo4j_user"], cfg["neo4j_password"]),
                                connection_timeout=4)


def status(cfg):
    try:
        with driver(cfg) as db:
            db.verify_connectivity()
        return True
    except Exception:
        return False


def sync_documents(cfg, store):
    from neo4j_graphrag.embeddings import OpenAIEmbeddings
    chunks = store.chunks(all_accounts=True)
    with driver(cfg) as db:
        db.execute_query("CREATE CONSTRAINT camzyos_chunk_id IF NOT EXISTS FOR (c:CamzyosChunk) "
                         "REQUIRE c.id IS UNIQUE", database_=cfg["neo4j_database"])
        db.execute_query("CREATE VECTOR INDEX camzyos_embeddings IF NOT EXISTS "
                         "FOR (c:CamzyosChunk) ON (c.embedding) OPTIONS {indexConfig: {"
                         "`vector.dimensions`: $dimensions, `vector.similarity_function`: 'cosine'}}",
                         dimensions=cfg["embedding_dimensions"], database_=cfg["neo4j_database"])
        existing = db.execute_query("MATCH(c:CamzyosChunk) WHERE c.embedding IS NOT NULL "
                                    "RETURN c.id AS id, c.embedding_model AS model",
                                    database_=cfg["neo4j_database"]).records
        ready = {r["id"] for r in existing if r["model"] == cfg["embedding_model"]}
        embedder = OpenAIEmbeddings(model=cfg["embedding_model"], api_key=cfg["api_key"],
                                    base_url=cfg["base_url"])
        for chunk in chunks:
            if chunk["id"] in ready:
                continue
            vector = embedder.embed_query(chunk["text"], dimensions=cfg["embedding_dimensions"])
            db.execute_query("MERGE(c:CamzyosChunk {id:$id}) SET c.text=$text,c.version_id=$version,"
                             "c.embedding=$vector,c.embedding_model=$model",
                             id=chunk["id"], text=chunk["text"], version=chunk["version_id"],
                             vector=vector, model=cfg["embedding_model"], database_=cfg["neo4j_database"])
    return len(chunks)


def vector_search(cfg, question, allowed):
    """Eligibility is applied in retrieval and again by allowed-ID intersection."""
    from neo4j_graphrag.embeddings import OpenAIEmbeddings
    from neo4j_graphrag.retrievers import VectorRetriever
    versions = sorted({c["version_id"] for c in allowed})
    if not versions:
        return []
    with driver(cfg) as db:
        retriever = VectorRetriever(
            db, "camzyos_embeddings", neo4j_database=cfg["neo4j_database"],
            embedder=OpenAIEmbeddings(model=cfg["embedding_model"], api_key=cfg["api_key"],
                                      base_url=cfg["base_url"]),
            return_properties=["id", "text"],
        )
        # raw_search keeps structured node IDs; never parse a string representation of a record.
        vector = retriever.embedder.embed_query(question, dimensions=cfg["embedding_dimensions"])
        result = retriever.get_search_results(query_vector=vector, top_k=cfg["retrieval_top_k"],
                                             filters={"version_id": {"$in": versions},
                                                      "embedding_model": cfg["embedding_model"]})
        return [record["node"]["id"] for record in result.records]


def group(hcp_id):
    if not hcp_id or not hcp_id.startswith("HCP_"):
        raise ValueError("A resolved HCP ID is required.")
    return "hcp_" + hcp_id


def memory_client(cfg):
    from graphiti_core import Graphiti
    from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
    from graphiti_core.driver.neo4j_driver import Neo4jDriver
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_client import OpenAIClient
    llm_config = LLMConfig(api_key=cfg["api_key"], model=cfg["model"],
                           small_model=cfg["model"], base_url=cfg["base_url"])
    return Graphiti(
        graph_driver=Neo4jDriver(cfg["neo4j_uri"], cfg["neo4j_user"], cfg["neo4j_password"],
                                 database=cfg["neo4j_database"]),
        llm_client=OpenAIClient(config=llm_config),
        cross_encoder=OpenAIRerankerClient(config=llm_config),
        embedder=OpenAIEmbedder(config=OpenAIEmbedderConfig(api_key=cfg["api_key"],
                                    embedding_model=cfg["embedding_model"],
                                    embedding_dim=cfg["embedding_dimensions"], base_url=cfg["base_url"])),
    )


async def memory(client, hcp_id, query=None, episode=None, seed=False):
    from graphiti_core.nodes import EpisodeType
    try:
        if episode is not None:
            await client.build_indices_and_constraints()
            episode_uuid = str(uuid5(NAMESPACE_URL, hcp_id + json.dumps(episode, sort_keys=True))) if seed else None
            if episode_uuid:
                records, _, _ = await client.driver.execute_query(
                    "MATCH(n:Episodic {uuid:$uuid,group_id:$group}) RETURN n.uuid AS uuid",
                    uuid=episode_uuid, group=group(hcp_id))
                if records:
                    return {"episode_uuid": episode_uuid, "status": "already imported"}
            result = await client.add_episode(
                name="Attributed HCP context", episode_body=json.dumps(episode, ensure_ascii=False),
                source=EpisodeType.json, source_description="HCP context, not clinical evidence",
                reference_time=datetime.now(timezone.utc), group_id=group(hcp_id), uuid=episode_uuid,
            )
            return {"episode_uuid": result.episode.uuid}
        edges = await client.search(query, group_ids=[group(hcp_id)], num_results=5)
        return [{"fact": edge.fact, "uuid": edge.uuid, "group_id": edge.group_id} for edge in edges
                if edge.group_id == group(hcp_id)]
    finally:
        await client.close()


def recall(cfg, hcp_id, query):
    # Construct outside the event loop: Neo4jDriver otherwise schedules a duplicate schema build.
    return asyncio.run(memory(memory_client(cfg), hcp_id, query=query))


def retain(cfg, hcp_id, episode, consent=False, seed=False):
    if not consent or not hcp_id:
        return None
    return asyncio.run(memory(memory_client(cfg), hcp_id, episode=episode, seed=seed))


def forget(cfg, hcp_id):
    with driver(cfg) as db:
        db.execute_query("MATCH(n {group_id:$group}) DETACH DELETE n", group=group(hcp_id),
                         database_=cfg["neo4j_database"])

