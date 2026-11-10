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
        self.assertIn("      - phase-0.2-planning", pull_block)
        self.assertIn("      - feat/station2-trust-manifest-rotation", pull_block)
        self.assertIn("      - feat/station2-monotonic-anchor-contract", pull_block)
        self.assertIn("      - feat/station2-atomic-activation-contract", pull_block)
        self.assertIn("      - feat/station2-config-schema-dumper", pull_block)
        self.assertIn("      - feat/station2-sqlite-anchor-reference", pull_block)
        self.assertIn("      - main", pull_block)


if __name__ == "__main__":
    unittest.main()
