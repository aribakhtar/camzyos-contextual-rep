"""Optional portable Windows Neo4j. No services, global Java changes or public ports."""
import argparse
import hashlib
import json
import os
import socket
import subprocess
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"


def download(url, target):
    if not target.exists():
        print(f"Downloading {target.name}", flush=True)
        partial = target.with_suffix(".part")
        with httpx.stream("GET", url, timeout=120, follow_redirects=True) as response:
            response.raise_for_status()
            with partial.open("wb") as output:
                for block in response.iter_bytes():
                    output.write(block)
        partial.replace(target)


def setup():
    RUNTIME.mkdir(exist_ok=True)
    url = ("https://api.adoptium.net/v3/assets/latest/21/hotspot?"
           "architecture=x64&image_type=jdk&os=windows&vendor=eclipse")
    cached = RUNTIME / "java-package.json"
    if cached.exists():
        package = json.loads(cached.read_text(encoding="utf-8-sig"))
    else:
        response = httpx.get(url, headers={"User-Agent": "camzyos-prototype/0.1"},
                             timeout=30, follow_redirects=True)
        response.raise_for_status()
        package = response.json()[0]["binary"]["package"]
    java_zip = RUNTIME / "java.zip"
    download(package["link"], java_zip)
    if hashlib.sha256(java_zip.read_bytes()).hexdigest() != package["checksum"]:
        raise RuntimeError("Java archive checksum mismatch; remove the failed archive before retrying.")
    if not list(RUNTIME.glob("jdk-*/bin/java.exe")):
        with zipfile.ZipFile(java_zip) as archive:
            archive.extractall(RUNTIME)
    neo_zip = RUNTIME / "neo4j.zip"
    download("https://dist.neo4j.org/neo4j-community-2026.10.1-windows.zip", neo_zip)
    if not list(RUNTIME.glob("neo4j-*/bin/neo4j.bat")):
        with zipfile.ZipFile(neo_zip) as archive:
            archive.extractall(RUNTIME)
    java = next(RUNTIME.glob("jdk-*/bin/java.exe")).parents[1]
    neo = next(RUNTIME.glob("neo4j-*/bin/neo4j.bat")).parents[1]
    env = {**os.environ, "JAVA_HOME": str(java), "NEO4J_HOME": str(neo)}
    from dotenv import dotenv_values
    password = dotenv_values(ROOT / ".env").get("NEO4J_PASSWORD")
    if not password:
        raise RuntimeError("Set a non-empty NEO4J_PASSWORD in .env before setup.")
    marker = RUNTIME / "initialized.json"
    if not marker.exists():
        config = neo / "conf/neo4j.conf"
        with config.open("a", encoding="utf-8") as f:
            f.write("\nserver.default_listen_address=127.0.0.1\n"
                    "server.memory.heap.initial_size=256m\nserver.memory.heap.max_size=512m\n"
                    "server.memory.pagecache.size=256m\n"
                    "dbms.usage_report.enabled=false\nserver.fleet_discovery.enabled=false\n"
                    "dbms.fleet_manager.enabled=false\n")
        result = subprocess.run([str(neo / "bin/neo4j-admin.bat"), "dbms", "set-initial-password", password],
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode:
            raise RuntimeError("Neo4j initialization failed; check Java and local configuration.")
        marker.write_text(json.dumps({"java": str(java), "neo4j": str(neo)}), encoding="utf-8")
    print("Portable Neo4j ready. Run: python scripts/local_neo4j.py start", flush=True)


def start():
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 7687)) == 0:
            print("A server already listens on port 7687; not starting another instance.")
            return
    state = json.loads((RUNTIME / "initialized.json").read_text(encoding="utf-8"))
    env = {**os.environ, "JAVA_HOME": state["java"], "NEO4J_HOME": state["neo4j"]}
    with (RUNTIME / "neo4j.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen([str(Path(state["neo4j"]) / "bin/neo4j.bat"), "console"],
                                   env=env, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    (RUNTIME / "neo4j.pid").write_text(str(process.pid))
    print(f"Neo4j launched on localhost; log: {RUNTIME / 'neo4j.log'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["setup", "start"])
    action = parser.parse_args().action
    setup() if action == "setup" else start()

