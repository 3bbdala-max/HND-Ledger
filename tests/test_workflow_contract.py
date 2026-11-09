"""Static regression checks for the repository CI trigger contract."""
from pathlib import Path
import re
import unittest


class WorkflowContractTests(unittest.TestCase):
    def test_planning_branch_push_and_pull_request_targets_run_ci(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "hnd-v02-tests.yml"
        ).read_text(encoding="utf-8")

        self.assertRegex(
            workflow,
            re.compile(
                r"(?m)^  push:\n    branches:\n      - phase-0\.2-planning$"
            ),
        )
        self.assertRegex(
            workflow,
            re.compile(
                r"(?m)^  pull_request:\n    branches:\n      - phase-0\.2-planning\n      - main$"
            ),
        )


if __name__ == "__main__":
    unittest.main()
