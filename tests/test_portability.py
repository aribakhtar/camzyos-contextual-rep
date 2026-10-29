import hashlib
import importlib
import json
import shutil

import pytest

from camzyos import ingest, profiles
from camzyos.settings import ROOT, sources
from camzyos.store import Store


@pytest.fixture
def portable_cfg(monkeypatch):
    module = importlib.import_module("camzyos.settings")
    monkeypatch.setattr(module, "load_dotenv", lambda *a, **k: None)
    for variable in ("DATA_DIR", "WORKBOOK_PATH", "PDF_DIR", "OPENAI_API_KEY", "NEO4J_PASSWORD"):
        monkeypatch.delenv(variable, raising=False)
    return module.settings()


def test_bundled_inputs_and_hcp_history(portable_cfg):
    entries = json.loads((ROOT / "assets/manifest.json").read_text(encoding="utf-8"))
    assert len(entries) == 9
    for entry in entries:
        path = ROOT / "assets" / entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    assert all((portable_cfg["pdf_dir"] / source["file"]).exists() for source in sources(portable_cfg))
    tables = profiles.load_profiles(portable_cfg["workbook"])
    assert len(tables["HCP_Profile"]) == 8
    assert len(tables["Personality"]) == 8
    assert len(tables["HCP_Interactions"]) == 41
    hcp = profiles.resolve_hcp(tables, "anna.weber@example-clinic.de")
    context = profiles.context(tables, hcp)
    assert context["profile"]["name"] == "Dr. Anna Weber"
    assert context["interactions"]
    assert all(row["hcp_id"] == hcp["hcp_id"] for row in context["interactions"])


def test_relative_paths_do_not_depend_on_working_directory(portable_cfg, monkeypatch, tmp_path):
    module = importlib.import_module("camzyos.settings")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WORKBOOK_PATH", "assets/hcp_context.xlsx")
    monkeypatch.setenv("PDF_DIR", "")  # Blank .env.example override must use config.yaml.
    cfg = module.settings()
    assert cfg["workbook"] == ROOT / "assets/hcp_context.xlsx"
    assert cfg["pdf_dir"] == ROOT / "assets/product_information"
    assert cfg["data_dir"] == ROOT / "data"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert module.settings()["data_dir"] == tmp_path


def test_fresh_prepare_works_without_secrets_or_original_folders(portable_cfg, tmp_path, monkeypatch):
    cfg = {**portable_cfg, "data_dir": tmp_path / "generated"}
    store = Store(cfg["data_dir"])
    catalog = sources(cfg)
    store.register(catalog)
    monkeypatch.setattr(ingest.httpx, "get", lambda *a, **k: pytest.fail("Prepare must work offline"))
    results = ingest.prepare_demo(cfg, store, catalog)
    assert len(results) == 8
    assert store.chunks()
    assert {c["source"]["id"] for c in store.chunks()} == {"eu_smpc"}
    assert all(v["status"] == "staged" for v in store.versions() if v["source_id"] != "eu_smpc")
    monkeypatch.setattr(ingest, "extract", lambda *a, **k: pytest.fail("Unchanged files must not reparse"))
    assert all(r["unchanged"] for r in ingest.prepare_demo(cfg, store, catalog))
    active = store.chunks()[0]["version_id"]
    store.deactivate(active)
    ingest.prepare_demo(cfg, store, catalog)
    assert store.chunks() == []  # Setup must not undo a deliberate withdrawal.


def test_changed_bundle_cannot_reuse_snapshot_review(portable_cfg, tmp_path):
    source = next(s for s in sources(portable_cfg) if s["id"] == "eu_smpc")
    path = tmp_path / source["file"]
    shutil.copyfile(portable_cfg["pdf_dir"] / source["file"], path)
    cfg = {**portable_cfg, "data_dir": tmp_path / "generated", "pdf_dir": tmp_path}
    store = Store(cfg["data_dir"])
    store.register([source])
    original = ingest.process(cfg, store, source)  # Remains staged, not active.
    with path.open("ab") as pdf:
        pdf.write(b"\n% changed fixture bytes\n")
    ingest.prepare_demo(cfg, store, [source])
    assert store.chunks() == []
    assert all(v["status"] == "staged" for v in store.versions())
    assert len(store.versions()) == 2
    assert original["version"] in {v["id"] for v in store.versions()}
