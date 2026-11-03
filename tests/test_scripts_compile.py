import py_compile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ScriptsCompileTests(unittest.TestCase):
    """Scripts run only on GitHub (the self-test, the nightly check) must at least be valid Python."""

    def test_every_script_compiles(self):
        for path in sorted((ROOT / "scripts").glob("*.py")):
            with self.subTest(script=path.name):
                py_compile.compile(str(path), doraise=True)


if __name__ == "__main__":
    unittest.main()
