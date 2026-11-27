"""Static regression checks for the repository CI trigger contract."""
from pathlib import Path
import unittest


class WorkflowContractTests(unittest.TestCase):
    def test_planning_branch_and_stacked_feature_branches_run_ci(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "hnd-v02-tests.yml"
        ).read_text(encoding="utf-8")
        lines = workflow.splitlines()
        push_start = lines.index("  push:")
        pull_start = lines.index("  pull_request:")
        jobs_start = lines.index("jobs:")
        push_block = lines[push_start:pull_start]
        pull_block = lines[pull_start:jobs_start]
        self.assertIn("      - phase-0.2-planning", push_block)
        self.assertIn("      - feat/station2-vsp-rotation-activation", push_block)
        self.assertIn("      - feat/station2-monotonic-anchor-contract", push_block)
        self.assertIn("      - feat/station2-atomic-activation-contract", push_block)
        self.assertIn("      - feat/station2-config-schema-dumper", push_block)
        self.assertIn("      - feat/station2-sqlite-anchor-reference", push_block)
        self.assertIn("      - feat/station2-sqlite-atomic-activation-reference", push_block)
        self.assertIn("      - fix/station2-sqlite-backend-monotonic-enforcement", push_block)
        self.assertIn("      - feat/station2-etcd-atomic-activation-backend", push_block)
        self.assertIn("      - station2-witness-backend-interface", push_block)
        self.assertIn("      - fix/station2-sqlite-anchor-direct-monotonic", push_block)
        self.assertIn("      - phase-0.2-planning", pull_block)
        self.assertIn("      - feat/station2-trust-manifest-rotation", pull_block)
        self.assertIn("      - feat/station2-monotonic-anchor-contract", pull_block)
        self.assertIn("      - feat/station2-atomic-activation-contract", pull_block)
        self.assertIn("      - feat/station2-config-schema-dumper", pull_block)
        self.assertIn("      - feat/station2-sqlite-anchor-reference", pull_block)
        self.assertIn("      - feat/station2-sqlite-atomic-activation-reference", pull_block)
        self.assertIn("      - fix/station2-sqlite-backend-monotonic-enforcement", pull_block)
        self.assertIn("      - feat/station2-etcd-atomic-activation-backend", pull_block)
        self.assertIn("      - station2-witness-backend-interface", pull_block)
        self.assertIn("      - main", pull_block)


    def test_workflow_token_permissions_are_explicitly_read_only(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "hnd-v02-tests.yml"
        ).read_text(encoding="utf-8")
        lines = workflow.splitlines()
        permissions_start = lines.index("permissions:")
        jobs_start = lines.index("jobs:")
        permissions_block = [
            line for line in lines[permissions_start:jobs_start] if line.strip()
        ]
        self.assertEqual(
            permissions_block,
            ["permissions:", "  contents: read"],
        )


    def test_external_and_noise_smokes_cover_all_four_remote_signers(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "hnd-v02-tests.yml"
        ).read_text(encoding="utf-8")
        commands = [
            line.strip()
            for line in workflow.splitlines()
            if line.strip().startswith(
                "run: python scripts/cometbft_v040_four_validator_network_smoke.py"
            )
        ]
        external = [
            line for line in commands
            if "--remote-signer-binary" in line
            and "--remote-only-binary" in line
        ]
        noise = [
            line for line in commands
            if "--noise-remote-signer-binary" in line
            and "--remote-only-binary" in line
        ]
        self.assertTrue(
            any("--all-remote-signers" in line for line in external),
            "external remote-signer smoke must exercise all four validators",
        )
        self.assertTrue(
            any("--all-remote-signers" in line for line in noise),
            "authenticated Noise smoke must exercise all four validators",
        )

    def test_workflow_actions_are_pinned_to_full_commit_shas(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "hnd-v02-tests.yml"
        ).read_text(encoding="utf-8")
        references = []
        for line in workflow.splitlines():
            stripped = line.strip()
            if stripped.startswith("uses:"):
                reference = stripped.split("@", 1)[1].split()[0]
                self.assertRegex(
                    reference,
                    r"^[0-9a-f]{40}$",
                    msg=f"GitHub Action must use a full commit SHA: {stripped}",
                )
                references.append(reference)
        self.assertGreater(len(references), 0)

    def test_hrec03_pre_rename_crash_boundary_is_executed_in_ci(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "hnd-v02-tests.yml"
        ).read_text(encoding="utf-8")
        start = workflow.index("- name: Run isolated v0.2 tests")
        end = workflow.index("\n\n  cometbft-single-node-smoke:", start)
        self.assertIn(
            "tests.test_hrec03_pre_rename_crash_boundary",
            workflow[start:end],
            "HREC03 pre-rename crash-boundary regression must run in CI",
        )


    def test_abci_store_durability_tests_are_executed_in_ci(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "hnd-v02-tests.yml"
        ).read_text(encoding="utf-8")
        start = workflow.index("- name: Run isolated v0.2 tests")
        end = workflow.index("\n\n  cometbft-single-node-smoke:", start)
        self.assertIn(
            "tests.test_v02_abci_app",
            workflow[start:end],
            "ABCI store fsync-order and post-replace recovery tests must run in CI",
        )


    def test_standalone_ledger_durability_tests_are_executed_in_ci(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "hnd-v02-tests.yml"
        ).read_text(encoding="utf-8")
        start = workflow.index("- name: Run isolated v0.2 tests")
        end = workflow.index("\n\n  cometbft-single-node-smoke:", start)
        self.assertIn(
            "tests.test_v02_ledger",
            workflow[start:end],
            "standalone ledger fsync-order and retry tests must run in CI",
        )


    def test_four_validator_harness_uses_guarded_disposable_abci_server(self):
        root = Path(__file__).resolve().parents[1]
        smoke = (root / "scripts" / "cometbft_v040_four_validator_network_smoke.py").read_text(
            encoding="utf-8"
        )
        production_server = (root / "hnd_v02" / "cometbft_v040_server.py").read_text(
            encoding="utf-8"
        )
        workflow = (root / ".github" / "workflows" / "hnd-v02-tests.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("hnd_v02_test_abci_server.py", smoke)
        self.assertNotIn('"hnd_v02.cometbft_v040_server"', smoke)
        self.assertIn('app_env["HND_DISPOSABLE_ABCI_TEST_SERVER"] = "1"', smoke)
        self.assertIn('"--initialize-genesis"', smoke)
        self.assertIn('"--recovery"', smoke)
        self.assertIn("standalone ABCI startup is disabled", production_server)
        self.assertIn("tests.test_disposable_abci_server", workflow)


    def test_station2_activation_and_recovery_reference_tests_are_executed_in_ci(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "hnd-v02-tests.yml"
        ).read_text(encoding="utf-8")
        start = workflow.index("- name: Run Station 2 activation and recovery reference tests")
        end = workflow.index("\n\n  cometbft-single-node-smoke:", start)
        station2_step = workflow[start:end]
        required_modules = (
            "tests.test_activation_bundle",
            "tests.test_activation_bundle_rotation",
            "tests.test_activation_coordinator",
            "tests.test_activation_transaction",
            "tests.test_monotonic_anchor",
            "tests.test_remote_activation_intent",
            "tests.test_remote_activation_intent_server",
            "tests.test_remote_monotonic_anchor",
            "tests.test_remote_monotonic_anchor_server",
            "tests.test_sqlite_activation_intent_store",
            "tests.test_sqlite_atomic_activation",
            "tests.test_sqlite_monotonic_anchor",
            "tests.test_station2_end_to_end_activation",
        )
        for module in required_modules:
            with self.subTest(module=module):
                self.assertIn(
                    module,
                    station2_step,
                    f"{module} must remain in the Station 2 CI test matrix",
                )


    def test_p2p_evidence_harness_uses_disposable_abci_server(self):
        root = Path(__file__).resolve().parents[1]
        harness = (
            root / "scripts" / "cometbft_v040_hnd_p2p_evidence_integration.py"
        ).read_text(encoding="utf-8")
        self.assertIn("hnd_v02_test_abci_server.py", harness)
        self.assertNotIn('sys.executable, "-m", "hnd_v02.cometbft_v040_server"', harness)
        self.assertIn('app_env["HND_DISPOSABLE_ABCI_TEST_SERVER"] = "1"', harness)
        self.assertIn('"--initialize-genesis"', harness)
        self.assertIn('"--recovery"', harness)


if __name__ == "__main__":
    unittest.main()
