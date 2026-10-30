"""Optional portable Windows Neo4j. No services, global Java changes or public ports."""
import argparse
import ctypes
import hashlib
import json
import math
import os
import socket
import subprocess
import sys
import time
import zipfile
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"


class WindowsConsole:
    """Only query/synchronize access; deliberately no process termination API."""

    def __init__(self):
        if os.name != "nt":
            raise RuntimeError("Portable Neo4j start/stop requires Windows.")
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "OpenProcess": (wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
            "CloseHandle": (wintypes.BOOL, [wintypes.HANDLE]),
            "GetProcessTimes": (wintypes.BOOL, [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4),
            "QueryFullProcessImageNameW": (wintypes.BOOL, [wintypes.HANDLE, wintypes.DWORD,
                                                        wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]),
            "WaitForSingleObject": (wintypes.DWORD, [wintypes.HANDLE, wintypes.DWORD]),
            "AttachConsole": (wintypes.BOOL, [wintypes.DWORD]),
            "FreeConsole": (wintypes.BOOL, []),
            "SetConsoleCtrlHandler": (wintypes.BOOL, [ctypes.c_void_p, wintypes.BOOL]),
            "GetConsoleProcessList": (wintypes.DWORD, [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]),
            "GenerateConsoleCtrlEvent": (wintypes.BOOL, [wintypes.DWORD, wintypes.DWORD]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.api, name)
            function.restype, function.argtypes = result, arguments

    @staticmethod
    def check(result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    def open(self, pid):
        # PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, never PROCESS_TERMINATE.
        handle = self.api.OpenProcess(0x1000 | 0x100000, False, pid)
        if not handle and ctypes.get_last_error() == 87:  # ERROR_INVALID_PARAMETER: exited PID
            return None
        return self.check(handle)

    def close(self, handle):
        self.api.CloseHandle(handle)

    def identity(self, handle, pid):
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        self.check(self.api.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                           ctypes.byref(kernel), ctypes.byref(user)))
        size = wintypes.DWORD(32768)
        image = ctypes.create_unicode_buffer(size.value)
        self.check(self.api.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)))
        return {"pid": pid, "created": (created.dwHighDateTime << 32) | created.dwLowDateTime,
                "image": os.path.normcase(image.value)}

    def running(self, handle):
        result = self.api.WaitForSingleObject(handle, 0)
        if result == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        return result == 258  # WAIT_TIMEOUT

    def attach(self, pid):
        self.check(self.api.AttachConsole(pid))

    def ignore_ctrl_c(self):
        # AttachConsole resets handlers; install this AFTER attaching, in the worker only.
        self.check(self.api.SetConsoleCtrlHandler(None, True))

    def members(self):
        size = 16
        while True:
            pids = (wintypes.DWORD * size)()
            count = self.check(self.api.GetConsoleProcessList(pids, size))
            if count <= size:
                return set(pids[:count]) - {os.getpid()}
            size = count

    def interrupt(self):
        # CTRL_C_EVENT cannot target a process group. The validated console is isolated.
        # https://learn.microsoft.com/en-us/windows/console/generateconsolectrlevent
        self.check(self.api.GenerateConsoleCtrlEvent(0, 0))

    def detach(self):
        self.api.FreeConsole()


@contextmanager
def runtime_lock():
    """Serialize start/stop without stale lock files blocking subsequent invocations."""
    import msvcrt

    with (RUNTIME / "neo4j.lock").open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError("Another local Neo4j start/stop is in progress; retry later.") from None
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def read_process_state():
    path = RUNTIME / "neo4j.pid"
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        valid = (isinstance(state, dict) and state.get("version") == 1
                 and state.get("console") == "isolated"
                 and state.get("owner") == str(Path(__file__).resolve())
                 and isinstance(state.get("processes"), list) and bool(state["processes"]))
        if valid:
            valid = all(isinstance(p, dict) and type(p.get("pid")) is int and 0 < p["pid"] < 0xFFFFFFFF
                        and type(p.get("created")) is int and p["created"] > 0
                        and isinstance(p.get("image"), str) and bool(p["image"])
                        for p in state["processes"])
        if valid:
            valid = len({p["pid"] for p in state["processes"]}) == len(state["processes"])
        if not valid:
            raise ValueError
    except (ValueError, UnicodeError):
        raise RuntimeError("Unverifiable or legacy neo4j.pid; refusing to signal any process. "
                           "Verify the old instance has exited before removing this file.") from None
    return state


def write_process_state(state):
    temporary = RUNTIME / "neo4j.pid.tmp"
    temporary.write_text(json.dumps(state), encoding="utf-8")
    temporary.replace(RUNTIME / "neo4j.pid")


@contextmanager
def owned_processes(windows, state):
    """Keep handles open through validation/signalling to protect against PID reuse."""
    handles = {}
    try:
        for expected in state["processes"]:
            pid = expected["pid"]
            handle = windows.open(pid)
            if handle is None:
                continue
            handles[pid] = handle
            if windows.identity(handle, pid) != expected:
                raise RuntimeError("Process identity changed (possibly a reused PID); refusing to signal. "
                                   "The ownership record was retained for inspection.")
        yield handles
    finally:
        for handle in handles.values():
            windows.close(handle)


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
    windows = WindowsConsole()
    with runtime_lock():
        _start(windows)


def _start(windows):
    previous = read_process_state()
    if previous:
        with owned_processes(windows, previous) as handles:
            if any(windows.running(handle) for handle in handles.values()):
                print("The managed Neo4j console is already running (possibly still starting).")
                return
        raise RuntimeError("The recorded launcher has exited. Run stop to clear its record before starting again.")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 7687)) == 0:
            print("A server already listens on port 7687; not starting another instance.")
            return
    state = json.loads((RUNTIME / "initialized.json").read_text(encoding="utf-8"))
    env = {**os.environ, "JAVA_HOME": state["java"], "NEO4J_HOME": state["neo4j"]}
    # Avoid cmd.exe's hidden "Terminate batch job (Y/N)?" prompt. The wrapper
    # restores Ctrl-C handling before either Neo4j JVM inherits its environment.
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    command = [str(powershell), "-NoProfile", "-NonInteractive", "-NoLogo", "-ExecutionPolicy", "Bypass",
               "-File", str(Path(__file__).with_name("local_neo4j_console.ps1")),
               "-Neo4jHome", state["neo4j"]]
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    with (RUNTIME / "neo4j.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(command, env=env, cwd=ROOT, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, startupinfo=startup,
                                   creationflags=subprocess.CREATE_NEW_CONSOLE)
        # Popen retains the original Windows process handle, even if the child exits.
        # Record identity from that handle, never from a fresh lookup of a bare PID.
        identity = windows.identity(int(process._handle), process.pid)
        write_process_state({"version": 1, "console": "isolated", "owner": str(Path(__file__).resolve()),
                             "processes": [identity]})
    if process.poll() is not None:
        raise RuntimeError("Neo4j launcher exited; inspect .runtime/neo4j.log.")
    print(f"Neo4j launched on localhost; log: {RUNTIME / 'neo4j.log'}")


def stop(timeout=60):
    if os.name != "nt":
        raise RuntimeError("Portable Neo4j start/stop requires Windows.")
    # Attach in a disposable worker with no console. Never detach the user's terminal
    # or temporarily change its Ctrl-C handling. The worker has its own bounded wait.
    # Pipes keep diagnostics visible even after the worker attaches to a hidden console.
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "stop", "--_console-worker",
                            "--timeout", str(timeout)], stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                           creationflags=subprocess.CREATE_NO_WINDOW)
    print(result.stdout, end="", flush=True)
    print(result.stderr, end="", file=sys.stderr, flush=True)
    return result.returncode


def stop_console(timeout):
    windows = WindowsConsole()
    if not RUNTIME.exists():
        print("No managed Neo4j process record; no signal sent.")
        return
    with runtime_lock():
        state = read_process_state()
        if state is None:
            print("No managed Neo4j process record; no signal sent.")
            return
        with owned_processes(windows, state) as handles:
            running = [pid for pid, handle in handles.items() if windows.running(handle)]
            if not running:
                (RUNTIME / "neo4j.pid").unlink()
                print("Recorded processes have exited; cleared their record. No signal sent.")
                return
            # A retained Java identity can be used after a timeout if the launcher has exited.
            target = running[0]
            # A Windows venv redirector may allocate a console for its interpreter
            # child despite CREATE_NO_WINDOW. Detach only this disposable worker.
            windows.detach()
            windows.attach(target)
            try:
                windows.ignore_ctrl_c()
                installed = json.loads((RUNTIME / "initialized.json").read_text(encoding="utf-8"))
                allowed_images = {state["processes"][0]["image"],
                                  os.path.normcase(str(Path(installed["java"]) / "bin/java.exe"))}
                oldest = min(p["created"] for p in state["processes"])

                def remember_members(members):
                    new_members = members - handles.keys()
                    for pid in new_members:
                        handle = windows.open(pid)
                        if handle is None:
                            raise RuntimeError("Console processes changed during validation; retry stop.")
                        handles[pid] = handle
                        identity = windows.identity(handle, pid)
                        if identity["image"] not in allowed_images or identity["created"] < oldest:
                            raise RuntimeError("Unexpected process in the console; refusing to signal it.")
                        state["processes"].append(identity)
                    # Preserve child identities before signalling, including across a timeout.
                    if new_members:
                        write_process_state(state)

                members = windows.members()
                if target not in members or not windows.running(handles[target]):
                    raise RuntimeError("The owned process left its console; retry stop. No signal sent.")
                remember_members(members)
                if windows.members() != members or not windows.running(handles[target]):
                    raise RuntimeError("Console processes changed during validation; retry stop. No signal sent.")
                windows.interrupt()
                print("Ctrl-C sent to the owned Neo4j console; waiting for shutdown...", flush=True)
                deadline = time.monotonic() + timeout
                while True:
                    members = windows.members()
                    remember_members(members)
                    if not members and not any(windows.running(handle) for handle in handles.values()):
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError(f"Shutdown not confirmed within {timeout:g}s; process record retained. "
                                           "Inspect .runtime/neo4j.log and retry stop.")
                    time.sleep(0.1)
                (RUNTIME / "neo4j.pid").unlink()
                print("Neo4j console processes exited after Ctrl-C.")
            finally:
                windows.detach()


def positive_timeout(value):
    try:
        timeout = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("timeout must be a positive number of seconds") from None
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be a finite, positive number of seconds")
    return timeout


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["setup", "start", "stop"])
    parser.add_argument("--timeout", type=positive_timeout, default=60,
                        help="seconds to wait for graceful stop (default: 60); never force-kills")
    parser.add_argument("--_console-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.action == "setup":
            setup()
        elif args.action == "start":
            start()
        elif args._console_worker:
            stop_console(args.timeout)
        else:
            return stop(args.timeout)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Local Neo4j: {exc} No process was force-killed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

