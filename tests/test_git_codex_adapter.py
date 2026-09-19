import concurrent.futures
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import git_codex_adapter as adapter  # noqa: E402


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


class GitCodexAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.repo = root / "repo"
        self.state = root / "state"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Fixture Author")
        git(self.repo, "config", "user.email", "fixture@example.invalid")
        self.contract = {
            "adapter": "design-ledger/git-codex",
            "schema_version": "0.4",
            "project": {"id": "fixture-product"},
            "repository": {"id": "fixture"},
            "risk_rules": [
                {"id": "ui", "paths": ["ui/**"], "risk": "high", "invalidates": ["ui"]},
                {"id": "docs", "paths": ["docs/**"], "risk": "low", "invalidates": ["docs"]},
            ],
            "default_rule": {"risk": "medium", "invalidates": ["source"]},
            "checks": [
                {
                    "id": "ui-check", "proof_class": "ui", "kind": "command",
                    "inputs": ["ui/**"],
                    "command": [sys.executable, "-c", "from pathlib import Path; assert Path('ui/view.txt').read_text()"],
                    "required_at": ["pre-push"],
                },
                {
                    "id": "docs-check", "proof_class": "docs", "kind": "command",
                    "inputs": ["docs/**"],
                    "command": [sys.executable, "-c", "from pathlib import Path; assert Path('docs/readme.md').read_text()"],
                    "required_at": ["pre-push"],
                },
            ],
        }
        (self.repo / "ui").mkdir()
        (self.repo / "docs").mkdir()
        (self.repo / "ui" / "view.txt").write_text("one\n", encoding="utf-8")
        (self.repo / "docs" / "readme.md").write_text("one\n", encoding="utf-8")
        self.commit("baseline")

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, message):
        git(self.repo, "add", "ui/view.txt", "docs/readme.md")
        git(self.repo, "commit", "-qm", message)
        return git(self.repo, "rev-parse", "HEAD")

    def ingest(self, commit="HEAD"):
        return adapter.ingest(self.repo, self.contract, self.state, commit)

    def test_concurrent_ingest_preserves_every_event(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            events = list(pool.map(lambda _: self.ingest(), range(24)))
        paths = adapter.state_paths(self.repo.resolve(), self.state, "fixture", "fixture-product")
        stored = adapter.json_records(paths["events"], adapter.RECORD_EVENT)
        self.assertEqual(24, len(stored))
        self.assertEqual(24, len({event["id"] for event in events}))
        self.assertIn("primary_actor", events[0]["source"]["attribution"])
        self.assertGreaterEqual(len(events[0]["source"]["attribution"]["actors"]), 1)
        written = adapter.process(self.repo, self.contract, self.state)
        self.assertEqual(1, len(written))
        self.assertEqual(24, len(written[0][1]["source"]["events"]))

    def test_rapid_linear_commits_coalesce_and_union_changes(self):
        (self.repo / "ui" / "view.txt").write_text("two\n", encoding="utf-8")
        first = self.commit("ui")
        self.ingest(first)
        (self.repo / "docs" / "readme.md").write_text("two\n", encoding="utf-8")
        second = self.commit("docs")
        self.ingest(second)
        written = adapter.process(self.repo, self.contract, self.state)
        self.assertEqual(1, len(written))
        receipt = written[0][1]
        self.assertEqual(second, receipt["source"]["commit"])
        self.assertEqual(2, len(receipt["source"]["events"]))
        self.assertEqual(["docs/readme.md", "ui/view.txt"], receipt["changes"])
        self.assertEqual(["baseline", "docs", "ui"], receipt["classification"]["rules"])

    def test_observe_is_idempotent_for_an_already_processed_commit(self):
        first_event, first_receipts = adapter.observe(
            self.repo, self.contract, self.state
        )
        second_event, second_receipts = adapter.observe(
            self.repo, self.contract, self.state
        )
        self.assertIsNotNone(first_event)
        self.assertEqual(1, len(first_receipts))
        self.assertIsNone(second_event)
        self.assertEqual([], second_receipts)

    def test_plugin_hook_observes_adapter_enabled_repository(self):
        contract_dir = self.repo / ".design-ledger"
        contract_dir.mkdir()
        (contract_dir / "adapter.json").write_text(
            json.dumps(self.contract), encoding="utf-8"
        )
        env = os.environ.copy()
        env["DESIGN_LEDGER_RUNTIME"] = str(ROOT / "runtime" / "git_codex_adapter.py")
        env["DESIGN_LEDGER_STATE_ROOT"] = str(self.state)
        result = subprocess.run(
            [sys.executable, str(ROOT / "plugins" / "design-ledger" / "scripts" / "ambient.py")],
            input=json.dumps({"cwd": str(self.repo)}), text=True,
            capture_output=True, env=env, check=False,
        )
        self.assertEqual(0, result.returncode)
        paths = adapter.paths_for_contract(self.repo.resolve(), self.state, self.contract)
        self.assertEqual(1, len(adapter.json_records(paths["events"], adapter.RECORD_EVENT)))
        self.assertEqual(1, len(adapter.json_records(paths["receipts"], adapter.RECORD_RECEIPT)))

    def test_install_sync_produces_self_contained_runtime_and_plugin(self):
        root = pathlib.Path(self.tmp.name) / "install"
        runtime_home = root / "runtime"
        plugin_home = root / "plugin"
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "sync_codex_install.py"),
                "sync",
                "--runtime-home",
                str(runtime_home),
                "--plugin-home",
                str(plugin_home),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        help_result = subprocess.run(
            [sys.executable, str(runtime_home / "git_codex_adapter.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, help_result.returncode, help_result.stderr)
        self.assertTrue((plugin_home / "hooks" / "hooks.json").is_file())

    def test_print_hook_targets_stable_cli_wrapper(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "runtime" / "git_codex_adapter.py"),
                "print-hook",
                "--adapter",
                str(ROOT / ".design-ledger" / "adapter.json"),
                "--state-root",
                str(pathlib.Path(self.tmp.name) / "state"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("runtime/git_codex_adapter.py", result.stdout)
        self.assertNotIn("runtime/design_ledger/cli.py", result.stdout)
        syntax = subprocess.run(
            ["sh", "-n"], input=result.stdout, text=True,
            capture_output=True, check=False,
        )
        self.assertEqual(0, syntax.returncode, syntax.stderr)

    def test_unchanged_inputs_reuse_accepted_result(self):
        self.ingest()
        baseline = adapter.process(self.repo, self.contract, self.state)[0][1]
        self.assertEqual({"passed"}, {item["status"] for item in baseline["checks"]})
        (self.repo / "docs" / "readme.md").write_text("two\n", encoding="utf-8")
        self.commit("docs only")
        self.ingest()
        receipt = adapter.process(self.repo, self.contract, self.state)[0][1]
        states = {item["id"]: item["status"] for item in receipt["checks"]}
        self.assertEqual("reused", states["ui-check"])
        self.assertEqual("passed", states["docs-check"])
        self.assertEqual(["docs"], receipt["classification"]["invalidates"])

    def test_unaffected_queued_check_is_not_requeued_and_late_evidence_reuses(self):
        self.contract["checks"].append({
            "id": "ui-agent", "proof_class": "ui", "kind": "codex",
            "inputs": ["ui/**"], "required_at": ["pr-readiness"],
        })
        base = git(self.repo, "rev-parse", "HEAD")
        self.ingest(base)
        first = adapter.process(self.repo, self.contract, self.state)[0][1]
        self.assertEqual("queued", next(item for item in first["checks"] if item["id"] == "ui-agent")["status"])
        (self.repo / "docs" / "readme.md").write_text("two\n", encoding="utf-8")
        self.commit("docs only")
        self.ingest()
        second = adapter.process(self.repo, self.contract, self.state)[0][1]
        self.assertNotIn("ui-agent", {item["id"] for item in second["checks"]})
        result, code = adapter.checkpoint(self.repo, self.contract, self.state, "pr-readiness")
        self.assertEqual(("Blocked", 2), (result["state"], code))
        adapter.record_evidence(
            self.repo, self.contract, self.state, base, "ui-agent", "passed",
            "Fixture Agent", "agent", "source-bound fixture review"
        )
        result, code = adapter.checkpoint(self.repo, self.contract, self.state, "pr-readiness")
        self.assertEqual(("Ready", 0), (result["state"], code))

    def test_checkpoint_requires_explicit_human_evidence(self):
        self.contract["checks"].append({
            "id": "release-approval", "proof_class": "release", "kind": "human",
            "inputs": ["ui/**"], "required_at": ["release"],
        })
        self.ingest()
        adapter.process(self.repo, self.contract, self.state)
        result, code = adapter.checkpoint(self.repo, self.contract, self.state, "release")
        self.assertEqual("Blocked", result["state"])
        self.assertEqual(2, code)
        with self.assertRaises(adapter.AdapterError):
            adapter.record_evidence(
                self.repo, self.contract, self.state, "HEAD", "release-approval",
                "passed", "fixture-agent", "agent", "self-asserted"
            )
        adapter.record_evidence(
            self.repo, self.contract, self.state, "HEAD", "release-approval",
            "passed", "Fixture Human", "human", "explicit fixture decision"
        )
        result, code = adapter.checkpoint(self.repo, self.contract, self.state, "release")
        self.assertEqual("Ready", result["state"])
        self.assertEqual(0, code)

    def test_failed_critical_check_blocks_delivery_checkpoint(self):
        self.contract["checks"][0]["command"] = [sys.executable, "-c", "raise SystemExit(9)"]
        self.contract["checks"][0]["failure_severity"] = "P0"
        self.ingest()
        receipt = adapter.process(self.repo, self.contract, self.state)[0][1]
        self.assertEqual("P0", receipt["findings"][0]["severity"])
        result, code = adapter.checkpoint(self.repo, self.contract, self.state, "pre-push")
        self.assertEqual("Blocked", result["state"])
        self.assertEqual(2, code)

    def test_multiple_agents_require_quorum_and_conflicts_need_supersession(self):
        self.contract["checks"].append({
            "id": "architecture-review", "proof_class": "ui", "kind": "codex",
            "inputs": ["ui/**"], "required_at": ["pr-readiness"],
            "acceptance": {
                "minimum": 2, "authorities": ["agent"], "distinct_actors": True,
            },
        })
        self.ingest()
        adapter.process(self.repo, self.contract, self.state)
        adapter.record_evidence(
            self.repo, self.contract, self.state, "HEAD", "architecture-review",
            "passed", "Agent A", "agent", "review A", "agent:a"
        )
        result, code = adapter.checkpoint(self.repo, self.contract, self.state, "pr-readiness")
        self.assertEqual(("Blocked", 2), (result["state"], code))
        _, conflict = adapter.record_evidence(
            self.repo, self.contract, self.state, "HEAD", "architecture-review",
            "failed", "Agent B", "agent", "review B conflict", "agent:b"
        )
        result, code = adapter.checkpoint(self.repo, self.contract, self.state, "pr-readiness")
        self.assertEqual(("Blocked", 2), (result["state"], code))
        adapter.record_evidence(
            self.repo, self.contract, self.state, "HEAD", "architecture-review",
            "passed", "Agent B", "agent", "review B corrected", "agent:b",
            [conflict["id"]]
        )
        result, code = adapter.checkpoint(self.repo, self.contract, self.state, "pr-readiness")
        self.assertEqual(("Ready", 0), (result["state"], code))

    def test_experience_event_links_to_next_commit_and_remains_queryable(self):
        _, note = adapter.record_experience(
            self.repo, self.contract, self.state, "feedback",
            "The settings flow should preserve the current section after saving.",
            "Fixture Human", "human", "settings-save"
        )
        timeline = adapter.experience_timeline(
            self.repo, self.contract, self.state, "settings-save"
        )
        self.assertEqual([note["id"]], [item["id"] for item in timeline])
        (self.repo / "ui" / "view.txt").write_text("two\n", encoding="utf-8")
        self.commit("implement settings feedback")
        event = self.ingest()
        self.assertEqual([note["id"]], event["context"]["experience_events"])
        receipt = adapter.process(self.repo, self.contract, self.state)[0][1]
        self.assertEqual([note["id"]], receipt["source"]["experience_events"])
        with self.assertRaises(adapter.AdapterError):
            adapter.record_experience(
                self.repo, self.contract, self.state, "decision",
                "Agent-selected decision", "Fixture Agent", "agent"
            )

    def test_state_root_inside_repository_is_refused(self):
        with self.assertRaises(adapter.AdapterError):
            adapter.state_paths(self.repo.resolve(), self.repo / ".design-ledger-state", "fixture")

    def test_json_schemas_and_example_are_well_formed(self):
        for name in ("git-adapter.schema.json", "commit-event.schema.json", "evidence-receipt.schema.json", "experience-event.schema.json"):
            data = json.loads((ROOT / "schema" / name).read_text(encoding="utf-8"))
            self.assertEqual("object", data["type"])
        example = json.loads(
            (ROOT / "adapters" / "git-codex" / "v0.4" / "example-adapter.json").read_text(encoding="utf-8")
        )
        adapter.validate_contract(example)


if __name__ == "__main__":
    unittest.main()
