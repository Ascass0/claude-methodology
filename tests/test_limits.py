"""Tests of the line limit per file (SPEC-0020, ADR-0016)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

from mthlib import limits  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from mthlib.git import Git  # noqa: E402
from test_delegation import RepoTestCase  # noqa: E402

BASE = 'version = 1\n[commands]\ntest = ""\n'
CONFIG_PATH = ".claude/methodology.toml"


def text(count: int) -> str:
    return "x\n" * count


class ConfigTests(unittest.TestCase):
    def test_defaults_and_valid_exceptions(self):
        # verifies: SPEC-0020/AC-01
        section = parse(Path("."), BASE)["limits"]
        self.assertEqual(section["max_file_lines"], 1000)
        self.assertIn("**/generated/**", section["exclude"])
        cfg = parse(Path("."), BASE + '[[limits.exceptions]]\npath = "src/g.py"\nmax_lines = 1400\nreason = "grammar"\nrefs = "ADR-0001"\n')
        self.assertEqual(limits.validate(cfg["limits"]), [limits.Exemption("src/g.py", 1400, "grammar", "ADR-0001")])

    def test_incomplete_or_inconsistent_limits_fail_fast_naming_the_exception(self):
        # verifies: SPEC-0020/AC-01
        # verifies: SPEC-0020/FM-01
        head = BASE + "[[limits.exceptions]]\n"
        cases = {
            "(path = 'src/g.py')' necesita 'max_lines'": head + 'path = "src/g.py"\nreason = "x"\n',
            "(path = 'src/g.py')' necesita 'reason'": head + 'path = "src/g.py"\nmax_lines = 1400\n',
            "(path = 'src/g.py')' necesita 'reason' ": head + 'path = "src/g.py"\nmax_lines = 1400\nreason = "  "\n',
            "(path = 'src/g.py')': max_lines = 1000 no supera 'limits.max_file_lines' = 1000": head + 'path = "src/g.py"\nmax_lines = 1000\nreason = "x"\n',
            "(path = 'src/g.py')' tiene claves desconocidas: motivo": head + 'path = "src/g.py"\nmax_lines = 1400\nreason = "x"\nmotivo = "y"\n',
            "necesita 'path'": head + 'max_lines = 1400\nreason = "x"\n',
            "debe ser un entero de 1 o más": "[limits]\nmax_file_lines = 0\n",
        }
        for expected, body in cases.items():
            with self.subTest(expected=expected):
                with self.assertRaises(MthError) as raised:
                    parse(Path("."), BASE + body if body.startswith("[limits]") else body)
                self.assertIn(expected.strip(), raised.exception.message)


class MeasureTests(unittest.TestCase):
    def test_physical_lines_and_binary(self):
        # verifies: SPEC-0020/AC-02
        # verifies: SPEC-0020/FM-03
        # verifies: SPEC-0020/FM-05
        cases = [([], 0), ([b""], 0), ([b"a\n"], 1), ([b"a\nb"], 2), ([b"a"], 1), ([b"\n\n"], 2),
                 ([b"a\nb\n", b"c", b"d\n"], 3), ([b"a\r\nb\r\n"], 2)]
        for chunks, expected in cases:
            with self.subTest(chunks=chunks):
                self.assertEqual(limits.count_lines(iter(chunks)), expected)
        self.assertIsNone(limits.count_lines(iter([b"abc\n", b"de\0f\n"])))


class RatchetTests(unittest.TestCase):
    def evaluate(self, counts, base=None, exemptions=(), limit=10):
        return limits.evaluate(counts, limit, list(exemptions), base, CONFIG_PATH)

    def test_growth_is_an_error_and_the_rest_a_warning(self):
        # verifies: SPEC-0020/AC-04
        # verifies: SPEC-0020/AC-05
        # verifies: SPEC-0020/AC-06
        before = {"new.py": 0, "crossed.py": 8, "grown.py": 30, "same.py": 30, "shrunk.py": 40}
        errors, warnings = self.evaluate({"new.py": 12, "crossed.py": 11, "grown.py": 31, "same.py": 30, "shrunk.py": 35,
                                          "small.py": 3}, before.__getitem__)
        self.assertEqual({e.path for e in errors}, {"new.py", "crossed.py", "grown.py"})
        self.assertEqual({w.path for w in warnings}, {"same.py", "shrunk.py"})
        by_path = {e.path: e.message for e in errors}
        self.assertIn("0 → 12", by_path["new.py"])
        self.assertIn("supera el límite", by_path["crossed.py"])
        self.assertIn("crece estando ya por encima", by_path["grown.py"])

    def test_without_a_parent_long_files_only_warn(self):
        # verifies: SPEC-0020/AC-07
        # verifies: SPEC-0020/FM-06
        errors, warnings = self.evaluate({"a.py": 50}, None)
        self.assertEqual(errors, [])
        self.assertEqual([w.path for w in warnings], ["a.py"])

    def test_exceptions_have_a_ceiling_and_expire(self):
        # verifies: SPEC-0020/AC-09
        # verifies: SPEC-0020/AC-10
        waiver = limits.Exemption("gen/**", 40, "grammar", "")
        self.assertEqual(self.evaluate({"gen/a.py": 40}, {}.__getitem__, [waiver]), ([], []))
        errors, _ = self.evaluate({"gen/a.py": 41}, {}.__getitem__, [waiver])
        self.assertEqual([e.path for e in errors], ["gen/a.py"])
        self.assertIn("techo", errors[0].message)
        errors, _ = self.evaluate({"gen/a.py": 10, "other.py": 99}, {"other.py": 99}.__getitem__, [waiver])
        self.assertEqual([(e.path, "caducada" in e.message) for e in errors], [(CONFIG_PATH, True)])
        errors, _ = self.evaluate({}, None, [waiver])  # the file no longer exists
        self.assertIn("caducada", errors[0].message)

    def test_the_base_is_read_only_when_a_file_needs_it(self):
        # verifies: SPEC-0020/FM-02
        def unreadable(path):
            raise MthError("sin base")
        self.assertEqual(self.evaluate({"small.py": 3}, unreadable), ([], []))
        with self.assertRaises(MthError):
            self.evaluate({"big.py": 30}, unreadable)


class BranchTestCase(RepoTestCase):
    """A repository whose `development` holds a 60-line legacy file and a feature branch on top."""

    config = RepoTestCase.config + "[limits]\nmax_file_lines = 40\n"

    def setUp(self):
        super().setUp()
        self.write("src/legacy.py", text(60))
        self.write("data/blob.bin", "a\0" * 40)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "legacy")
        self.git("branch", "development")

    def trace(self, *args, ok=True):
        return self.mth("trace", *args, ok=ok)


class BranchTests(BranchTestCase):
    def test_touching_a_legacy_file_without_growing_it_only_warns(self):
        # verifies: SPEC-0020/AC-06
        # verifies: SPEC-0020/AC-11
        self.write("src/legacy.py", text(59) + "changed\n")
        out = self.trace()
        self.assertIn("1 ficheros por encima del límite de líneas: mth trace --limits los lista", out)
        self.assertNotIn("src/legacy.py", out)
        listed = self.trace("--limits")
        self.assertIn("src/legacy.py", listed)
        self.assertIn("la rama no lo hace crecer", listed)

    def test_growing_it_or_creating_a_long_file_is_an_error(self):
        # verifies: SPEC-0020/AC-04
        # verifies: SPEC-0020/AC-05
        self.write("src/legacy.py", text(61))
        out = self.trace(ok=False)
        self.assertRegex(out, r"src/legacy\.py:1: la rama hace que crece estando ya por encima del límite: 60 → 61")
        self.write("src/legacy.py", text(60))
        self.write("src/new.py", text(41))
        self.assertRegex(self.trace(ok=False), r"src/new\.py:1: la rama hace que supera el límite: 0 → 41")

    def test_a_detected_rename_is_compared_with_its_origin(self):
        # verifies: SPEC-0020/AC-05
        self.git("mv", "src/legacy.py", "src/moved.py")
        out = self.trace()
        self.assertNotIn("✗", out)
        self.assertIn("1 ficheros por encima", out)

    def test_binary_files_and_excluded_paths_are_not_measured(self):
        # verifies: SPEC-0020/AC-02
        # verifies: SPEC-0020/AC-03
        self.write(".gitattributes", "data/marked.dat -diff\n")
        self.write("data/marked.dat", text(80))
        self.write("src/generated/out.py", text(80))
        self.write("deps/x.lock", text(80))
        self.write("data/blob.bin", "a\0" * 80)
        out = self.trace()
        for name in ("marked.dat", "generated/out.py", "x.lock", "blob.bin"):
            self.assertNotIn(name, self.trace("--limits"))
        self.assertIn("1 ficheros por encima", out)  # only the legacy file is listed

    def test_a_branch_without_a_parent_never_fails_for_size(self):
        # verifies: SPEC-0020/AC-07
        self.git("checkout", "-q", "development")
        self.write("src/big.py", text(80))
        self.git("add", "-A")
        out = self.trace()
        self.assertNotIn("✗", out)
        self.assertIn("2 ficheros por encima", out)

    def test_an_unreadable_parent_is_an_error_naming_the_cause(self):
        # verifies: SPEC-0020/AC-08
        self.git("branch", "-D", "development")
        out = self.trace(ok=False)
        self.assertIn("No se puede calcular el punto de partida", out)
        self.assertIn("git fetch", out)

    def test_the_base_is_the_fork_point_not_the_tip_of_the_parent(self):
        # verifies: SPEC-0020/AC-05
        self.git("checkout", "-q", "development")
        self.write("src/legacy.py", text(70))  # the parent grew after the branch forked
        self.git("commit", "-qam", "grow on development")
        self.git("checkout", "-q", "feat/demo")
        self.write("src/legacy.py", text(65))  # +5 on the branch: below the parent's tip, above the fork point
        self.assertIn("60 → 65", self.trace(ok=False))

    def test_a_blob_that_git_cannot_read_is_an_error_not_an_empty_file(self):
        # verifies: SPEC-0020/FM-02
        git = Git(self.work)
        self.assertEqual(b"".join(git.blob_chunks("HEAD", "src/legacy.py")), text(60).encode())
        self.assertEqual(list(git.blob_chunks("HEAD", "src/never-existed.py")), [])
        with self.assertRaises(MthError) as raised:
            list(git.blob_chunks("0" * 40, "src/legacy.py"))
        self.assertIn("No se puede leer src/legacy.py", raised.exception.message)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads any file")
    def test_an_unreadable_file_names_itself(self):
        # verifies: SPEC-0020/AC-02
        path = self.write("src/locked.py", "x\n")
        path.chmod(0)
        self.addCleanup(lambda: path.exists() and path.chmod(0o644))
        out = self.trace(ok=False)
        self.assertIn("No se puede leer src/locked.py para medir sus líneas", out)

    def test_exceptions_in_the_configuration_apply_through_the_command(self):
        # verifies: SPEC-0020/AC-09
        # verifies: SPEC-0020/AC-10
        extra = '[[limits.exceptions]]\npath = "src/legacy.py"\nmax_lines = 65\nreason = "tabla"\n'
        self.write(".claude/methodology.toml", self.config + extra)
        self.write("src/legacy.py", text(65))
        self.assertNotIn("✗", self.trace())
        self.write("src/legacy.py", text(66))
        self.assertIn("superan el techo de su excepción (65)", self.trace(ok=False))
        self.write("src/legacy.py", text(5))
        self.assertIn("excepción caducada", self.trace(ok=False))


class DocumentationTests(unittest.TestCase):
    def test_principles_reviewer_and_evals_carry_the_rule(self):
        # verifies: SPEC-0020/AC-12
        plugin = HERE.parent / "plugins" / "methodology"
        self.assertIn("**Tamaño de fichero:**", (plugin / "PRINCIPLES.md").read_text(encoding="utf-8"))
        template = (plugin / "catalog/revisor-diseno/agent.md.tmpl").read_text(encoding="utf-8")
        self.assertIn("su `reason` debe sostenerse frente a la responsabilidad única", template)
        evals = (plugin / "catalog/revisor-diseno/evals.toml").read_text(encoding="utf-8")
        for case in ("excepcion-de-tamano-sin-motivo-que-se-sostenga", "excepcion-de-tamano-que-se-sostiene"):
            self.assertIn(f'name = "{case}"', evals)


class RepositoryTests(unittest.TestCase):
    def test_the_repository_meets_its_own_limit(self):
        # verifies: SPEC-0020/AC-13
        root = HERE.parent
        cfg = parse(root, (root / ".claude" / "methodology.toml").read_text(encoding="utf-8"))
        exemptions = limits.validate(cfg["limits"])
        import subprocess
        files = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout.split()
        counts = {}
        for rel in files:
            with (root / rel).open("rb") as handle:
                n = limits.count_lines(iter(lambda: handle.read(limits.CHUNK), b""))
            if n is not None:
                counts[rel] = n
        errors, _ = limits.evaluate({p: n for p, n in counts.items() if "generated" not in p}, cfg["limits"]["max_file_lines"],
                                    exemptions, lambda path: 0, CONFIG_PATH)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
