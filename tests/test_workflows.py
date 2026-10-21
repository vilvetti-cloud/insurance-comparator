"""Every GitHub Actions workflow must be valid YAML.

GitHub silently refuses a workflow it cannot parse: the nightly rules check
did not run on 20-21.10.2026 because of an unquoted ": " in a run command.
"""
from pathlib import Path
import unittest

import yaml

WORKFLOWS = sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.yml"))


class WorkflowSyntaxTests(unittest.TestCase):
    def test_workflows_are_valid_yaml_with_jobs(self):
        self.assertTrue(WORKFLOWS)
        for path in WORKFLOWS:
            with self.subTest(workflow=path.name):
                workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
                self.assertIsInstance(workflow, dict)
                self.assertTrue(workflow.get("jobs"))


if __name__ == "__main__":
    unittest.main()
