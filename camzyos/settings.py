import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def settings() -> dict:
    load_dotenv(ROOT / ".env", override=True)
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg["data_dir"] = Path(os.getenv("DATA_DIR", str(ROOT / cfg["data_dir"])))
    cfg["workbook"] = Path(os.getenv("WORKBOOK_PATH", str(ROOT / "data/input/hcp.xlsx")))
    cfg["pdf_dir"] = Path(os.getenv("PDF_DIR", str(ROOT / "data/input/product_information")))
    cfg["api_key"] = os.getenv("OPENAI_API_KEY", "")
    cfg["base_url"] = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    cfg["neo4j_uri"] = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    cfg["neo4j_user"] = os.getenv("NEO4J_USER", "neo4j")
    cfg["neo4j_password"] = os.getenv("NEO4J_PASSWORD", "")
    cfg["neo4j_database"] = os.getenv("NEO4J_DATABASE", "neo4j")
    return cfg


def sources(cfg: dict) -> list[dict]:
    return yaml.safe_load((ROOT / cfg["sources_file"]).read_text(encoding="utf-8"))["sources"]

