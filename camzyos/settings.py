import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def settings() -> dict:
    load_dotenv(ROOT / ".env", override=True)
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    for key, variable in (("data_dir", "DATA_DIR"), ("workbook", "WORKBOOK_PATH"), ("pdf_dir", "PDF_DIR")):
        path = Path(os.getenv(variable) or cfg[key]).expanduser()
        cfg[key] = path if path.is_absolute() else ROOT / path
    cfg["api_key"] = os.getenv("OPENAI_API_KEY", "")
    cfg["base_url"] = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    cfg["neo4j_uri"] = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    cfg["neo4j_user"] = os.getenv("NEO4J_USER", "neo4j")
    cfg["neo4j_password"] = os.getenv("NEO4J_PASSWORD", "")
    cfg["neo4j_database"] = os.getenv("NEO4J_DATABASE", "neo4j")
    return cfg


def sources(cfg: dict) -> list[dict]:
    return yaml.safe_load((ROOT / cfg["sources_file"]).read_text(encoding="utf-8"))["sources"]

