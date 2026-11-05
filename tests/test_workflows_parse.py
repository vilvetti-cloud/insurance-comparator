import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class WorkflowsParseTests(unittest.TestCase):
    """GitHub workflows run only on GitHub: a broken file would silently stop the nightly check."""

    def test_every_workflow_is_valid_yaml_with_jobs(self):
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            with self.subTest(workflow=path.name):
                workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
                self.assertTrue(workflow.get("jobs"))

    def test_nightly_check_tells_the_owner_when_it_fails(self):
        workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "source-check.yml").read_text(encoding="utf-8"))
        steps = workflow["jobs"]["check"]["steps"]
        self.assertTrue(any(step.get("if") == "failure()" and "gh issue create" in step.get("run", "")
                            for step in steps))


if __name__ == "__main__":
    unittest.main()
