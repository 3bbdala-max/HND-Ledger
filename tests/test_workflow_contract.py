"""Static regression checks for the repository CI trigger contract."""
from pathlib import Path
import re
import unittest


class WorkflowContractTests(unittest.TestCase):
    def test_planning_branch_and_stacked_feature_branches_run_ci(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "hnd-v02-tests.yml"
        ).read_text(encoding="utf-8")

        push = re.search(r"(?ms)^  push:\\n    branches:\\n(?P<body>.*?)(?=^  [A-Za-z_]+:|\\Z)", workflow)
        pull_request = re.search(r"(?ms)^  pull_request:\\n    branches:\\n(?P<body>.*?)(?=^  [A-Za-z_]+:|\\Z)", workflow)
        self.assertIsNotNone(push)
        self.assertIsNotNone(pull_request)
        self.assertIn("phase-0.2-planning", push.group("body"))
        self.assertIn("feat/station2-vsp-rotation-activation", push.group("body"))
        self.assertIn("phase-0.2-planning", pull_request.group("body"))
        self.assertIn("feat/station2-trust-manifest-rotation", pull_request.group("body"))
        self.assertIn("main", pull_request.group("body"))


if __name__ == "__main__":
    unittest.main()
