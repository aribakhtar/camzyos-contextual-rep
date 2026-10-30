"""Isolated helper tests: no Neo4j launch, signals, downloads, or real runtime access.

Also runnable with base Python while the application environment is installing:
python -m unittest discover -s tests -p test_local_neo4j.py
"""

import json
import os
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import local_neo4j as helper


class FakeWindows:
    def __init__(self, java):
        self.identities = {
            101: {"pid": 101, "created": 1000, "image": "powershell.exe"},
            202: {"pid": 202, "created": 2000, "image": os.path.normcase(str(java / "bin/java.exe"))},
        }
        self.alive = {101, 202}
        self.console_members = {101, 202}
        self.events = []
        self.auto_exit = True

    def open(self, pid):
        self.events.append(("open", pid))
        return pid if pid in self.alive else None

    def close(self, handle):
        self.events.append(("close", handle))

    def identity(self, handle, pid):
        return dict(self.identities[pid])

    def running(self, handle):
        return handle in self.alive

    def attach(self, pid):
        self.events.append(("attach", pid))

    def ignore_ctrl_c(self):
        self.events.append(("ignore",))

    def members(self):
        return set(self.console_members)

    def interrupt(self):
        # Ownership must already include the actual JVM before any signal is sent.
        recorded = helper.read_process_state()
        assert self.console_members <= {p["pid"] for p in recorded["processes"]}
        self.events.append(("interrupt",))
        if self.auto_exit:
            self.alive.clear()
            self.console_members.clear()

    def detach(self):
        self.events.append(("detach",))


class LocalNeo4jTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runtime = self.root / ".runtime"
        self.runtime.mkdir()
        self.java = self.runtime / "jdk-local"
        self.neo = self.runtime / "neo4j-local"
        self.initialized = json.dumps({"java": str(self.java), "neo4j": str(self.neo)})
        (self.runtime / "initialized.json").write_text(self.initialized, encoding="utf-8")
        self.windows = FakeWindows(self.java)
        self.replace(helper, "ROOT", self.root)
        self.replace(helper, "RUNTIME", self.runtime)
        self.replace(helper, "WindowsConsole", Mock(return_value=self.windows))
        self.replace(helper, "runtime_lock", nullcontext)
        self.replace(helper.subprocess, "Popen", Mock(side_effect=AssertionError("No real processes")))
        self.replace(helper.subprocess, "run", Mock(side_effect=AssertionError("No real processes")))
        self.replace(helper.socket, "socket", Mock(side_effect=AssertionError("No real sockets")))
        # Replace only the helper's clock, not the shared time module used by
        # background library threads (for example RAGAS analytics).
        self.replace(helper, "time", SimpleNamespace(monotonic=helper.time.monotonic,
                     sleep=Mock(side_effect=AssertionError("No real waits"))))

    def replace(self, target, name, value):
        patcher = patch.object(target, name, value, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def record(self, **changes):
        state = {"version": 1, "console": "isolated", "owner": str(Path(helper.__file__).resolve()),
                 "processes": [dict(self.windows.identities[101])]}
        state.update(changes)
        helper.write_process_state(state)
        return state

    def assert_no_signal(self):
        self.assertNotIn(("interrupt",), self.windows.events)

    def test_graceful_stop_records_and_waits_for_console_processes(self):
        self.record()
        helper.stop_console(60)
        self.assertEqual(self.windows.events.count(("interrupt",)), 1)
        self.assertLess(self.windows.events.index(("detach",)), self.windows.events.index(("attach", 101)))
        self.assertLess(self.windows.events.index(("attach", 101)), self.windows.events.index(("ignore",)))
        self.assertLess(self.windows.events.index(("ignore",)), self.windows.events.index(("interrupt",)))
        self.assertIn(("close", 101), self.windows.events)
        self.assertIn(("close", 202), self.windows.events)
        self.assertIn(("detach",), self.windows.events)
        self.assertFalse((self.runtime / "neo4j.pid").exists())
        self.assertEqual((self.runtime / "initialized.json").read_text(encoding="utf-8"), self.initialized)

    def test_waits_for_java_even_after_launcher_exits_and_java_detaches(self):
        self.record()

        def interrupt():
            self.windows.alive.remove(101)
            self.windows.console_members.clear()

        self.windows.interrupt = Mock(side_effect=interrupt)
        sleeping = self.replace(helper.time, "sleep", Mock(side_effect=lambda _: self.windows.alive.clear()))
        helper.stop_console(60)
        sleeping.assert_called_once()
        self.assertFalse((self.runtime / "neo4j.pid").exists())

    def test_missing_record_does_not_probe_or_signal_other_servers(self):
        helper.stop_console(60)
        self.assertEqual(self.windows.events, [])

    def test_already_exited_record_is_cleared_without_signal(self):
        self.record()
        self.windows.alive.clear()
        helper.stop_console(60)
        self.assert_no_signal()
        self.assertFalse((self.runtime / "neo4j.pid").exists())

    def test_legacy_corrupt_or_foreign_record_is_refused(self):
        states = ["101", "{", "null", "[]", json.dumps(self.record(console="shared")),
                  json.dumps(self.record(owner="another-checkout/local_neo4j.py")),
                  json.dumps(self.record(processes=[{"pid": -1, "created": 1000, "image": "java.exe"}]))]
        for contents in states:
            with self.subTest(contents=contents):
                (self.runtime / "neo4j.pid").write_text(contents, encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "Unverifiable or legacy"):
                    helper.stop_console(60)
                self.assert_no_signal()
                self.assertEqual((self.runtime / "neo4j.pid").read_text(encoding="utf-8"), contents)

    def test_reused_pid_or_changed_executable_is_refused_before_attach(self):
        for field, replacement in [("created", 9999), ("image", "unrelated-java.exe")]:
            with self.subTest(field=field):
                expected = self.record()
                original = self.windows.identities[101][field]
                self.windows.identities[101][field] = replacement
                with self.assertRaisesRegex(RuntimeError, "Process identity changed"):
                    helper.stop_console(60)
                self.windows.identities[101][field] = original
                self.assert_no_signal()
                self.assertNotIn(("attach", 101), self.windows.events)
                self.assertEqual(helper.read_process_state(), expected)

    def test_unexpected_console_member_is_not_signalled(self):
        self.record()
        self.windows.identities[202]["image"] = "some-other-install/java.exe"
        with self.assertRaisesRegex(RuntimeError, "Unexpected process"):
            helper.stop_console(60)
        self.assert_no_signal()
        self.assertIn(("detach",), self.windows.events)
        self.assertIn(("close", 202), self.windows.events)

    def test_target_must_still_belong_to_attached_console(self):
        self.record()
        self.windows.console_members.remove(101)
        with self.assertRaisesRegex(RuntimeError, "left its console"):
            helper.stop_console(60)
        self.assert_no_signal()

    def test_access_denied_or_unavailable_console_does_not_fall_back_to_kill(self):
        self.record()
        self.windows.attach = Mock(side_effect=OSError("Cannot attach console"))
        with self.assertRaisesRegex(OSError, "Cannot attach"):
            helper.stop_console(60)
        self.assert_no_signal()
        self.assertTrue((self.runtime / "neo4j.pid").exists())
        self.assertIn(("close", 101), self.windows.events)

    def test_timeout_preserves_child_identity_for_retry_after_launcher_exits(self):
        self.record()
        self.windows.auto_exit = False
        self.replace(helper.time, "monotonic", Mock(side_effect=[0, 61]))
        with self.assertRaisesRegex(RuntimeError, "Shutdown not confirmed"):
            helper.stop_console(60)
        self.assertEqual({p["pid"] for p in helper.read_process_state()["processes"]}, {101, 202})
        self.assertIn(("detach",), self.windows.events)
        self.windows.alive.remove(101)
        self.windows.console_members.remove(101)
        self.windows.auto_exit = True
        self.replace(helper.time, "monotonic", Mock(return_value=100))
        helper.stop_console(60)
        self.assertIn(("attach", 202), self.windows.events)
        self.assertFalse((self.runtime / "neo4j.pid").exists())

    def test_start_uses_hidden_isolated_console_and_preserves_setup(self):
        self.replace(helper.subprocess, "STARTUPINFO", lambda: SimpleNamespace(dwFlags=0, wShowWindow=1))
        self.replace(helper.subprocess, "STARTF_USESHOWWINDOW", 1)
        self.replace(helper.subprocess, "SW_HIDE", 0)
        self.replace(helper.subprocess, "CREATE_NEW_CONSOLE", 16)
        environment = patch.dict(os.environ, {"SystemRoot": str(self.root / "Windows")})
        environment.start()
        self.addCleanup(environment.stop)
        process = SimpleNamespace(pid=101, _handle=101, poll=lambda: None)
        popen = self.replace(helper.subprocess, "Popen", Mock(return_value=process))
        probe = Mock()
        probe.connect_ex.return_value = 1
        self.replace(helper.socket, "socket", Mock(return_value=nullcontext(probe)))
        (self.root / ".env").write_text("untouched synthetic credentials", encoding="utf-8")
        before_environment = dict(os.environ)
        helper.start()
        command = popen.call_args.args[0]
        options = popen.call_args.kwargs
        wrapper = Path(helper.__file__).with_name("local_neo4j_console.ps1")
        self.assertEqual(command[-4:], ["-File", str(wrapper), "-Neo4jHome", str(self.neo)])
        self.assertEqual(options["creationflags"], 16)
        self.assertEqual(options["startupinfo"].wShowWindow, 0)
        self.assertEqual(options["stdin"], helper.subprocess.DEVNULL)
        self.assertEqual(options["env"]["JAVA_HOME"], str(self.java))
        self.assertEqual(options["env"]["NEO4J_HOME"], str(self.neo))
        self.assertEqual(os.environ, before_environment)
        self.assertEqual(helper.read_process_state()["processes"], [self.windows.identities[101]])
        self.assertEqual((self.runtime / "initialized.json").read_text(encoding="utf-8"), self.initialized)
        self.assertEqual((self.root / ".env").read_text(encoding="utf-8"), "untouched synthetic credentials")
        probe.connect_ex.assert_called_once_with(("127.0.0.1", 7687))

    def test_start_does_not_duplicate_an_instance_still_booting(self):
        self.record()
        helper.start()
        helper.subprocess.Popen.assert_not_called()
        helper.socket.socket.assert_not_called()

    def test_occupied_port_does_not_create_ownership_for_unrelated_server(self):
        probe = Mock()
        probe.connect_ex.return_value = 0
        self.replace(helper.socket, "socket", Mock(return_value=nullcontext(probe)))
        helper.start()
        helper.subprocess.Popen.assert_not_called()
        self.assertFalse((self.runtime / "neo4j.pid").exists())

    @unittest.skipUnless(os.name == "nt", "Windows stop worker")
    def test_stop_runs_signaller_in_separate_consoleless_worker(self):
        run = self.replace(helper.subprocess, "run", Mock(return_value=SimpleNamespace(
            returncode=1, stdout="sent Ctrl-C", stderr="shutdown timed out")))
        stdout = self.replace(helper.sys, "stdout", Mock())
        stderr = self.replace(helper.sys, "stderr", Mock())
        self.assertEqual(helper.stop(12), 1)
        command = run.call_args.args[0]
        self.assertIn("--_console-worker", command)
        self.assertEqual(command[-2:], ["--timeout", "12"])
        self.assertEqual(run.call_args.kwargs["creationflags"], helper.subprocess.CREATE_NO_WINDOW)
        self.assertEqual(run.call_args.kwargs["stdout"], helper.subprocess.PIPE)
        self.assertEqual(run.call_args.kwargs["stderr"], helper.subprocess.PIPE)
        self.assertIn("sent Ctrl-C", "".join(call.args[0] for call in stdout.write.call_args_list))
        self.assertIn("shutdown timed out", "".join(call.args[0] for call in stderr.write.call_args_list))

    def test_cli_reports_failure_and_never_claims_force_kill(self):
        self.replace(helper, "stop", Mock(side_effect=RuntimeError("Cannot attach console")))
        self.replace(helper.sys, "stderr", Mock())
        self.assertEqual(helper.main(["stop"]), 1)
        written = "".join(call.args[0] for call in helper.sys.stderr.write.call_args_list)
        self.assertIn("Cannot attach console", written)
        self.assertIn("No process was force-killed", written)

    def test_timeout_must_be_positive_and_finite(self):
        for invalid in ["0", "-1", "nan", "inf", "wrong"]:
            with self.subTest(invalid=invalid), self.assertRaises(helper.argparse.ArgumentTypeError):
                helper.positive_timeout(invalid)


if __name__ == "__main__":
    unittest.main()
