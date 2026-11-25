"""Tests of the test labels and the single-test warning (SPEC-0019, ADR-0015)."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import test_mth  # noqa: E402
from mthlib import flow, testlabels, trace  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from test_delegation import SPEC_ID, RepoTestCase  # noqa: E402

def fx(text: str) -> str:
    """Fixture IDs are written as @@ and built here, so this file holds no ID of its own to trace."""
    return text.replace("@@", "SPEC-" + "9001")


def no_limits(root: Path) -> dict:
    """The git surface that the line limit uses, for a fake repository with no long files."""
    return {"root": root, "binary_by_attributes": lambda paths: set(), "current_branch": lambda: "development"}


def lines(*rows: str) -> str:
    return fx("\n".join(rows) + "\n")


SPEC_PATTERN = r"SPEC-\d{4}"
PY = r"^\s*(?:async\s+)?def\s+test\w*\s*\("
CONFIG = 'version = 1\n[commands]\ntest = ""\n'
# Fixtures are built line by line from strings so that this file does not contain test definitions of its own.
SPEC = fx("# @@ · A\n- Estado: aprobada\n- **AC-01**: uno\n- **AC-02**: dos\n")


def findings(files: dict[str, str], config: str = CONFIG) -> list[trace.Finding]:
    root = Path(tempfile.mkdtemp())
    try:
        for rel, text in files.items():
            test_mth._write(root / rel, text)
        names = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
        return trace.check(parse(root, config), names)
    finally:
        shutil.rmtree(root)


def label_findings(files: dict[str, str], config: str = CONFIG) -> list[str]:
    return [str(f) for f in findings(files, config) if "etiqueta" in f.message]


class ConfigTests(unittest.TestCase):
    def test_defaults_cover_python_js_ts_and_go(self):
        # verifies: SPEC-0019/AC-01
        patterns = parse(Path("."), CONFIG)["trace"]["test_patterns"]
        for path, opening in (("a/test_x.py", "def test_x(self):"), ("a/x.test.ts", "  it('does', () => {"),
                              ("a/x.spec.js", "test('does', () => {"), ("a/x.test.tsx", "  test.each([1])('does', () => {"),
                              ("a/x_test.go", "func TestX(t *testing.T) {")):
            with self.subTest(path=path):
                regex = testlabels.pattern_for(path, patterns)
                self.assertIsNotNone(regex)
                self.assertRegex(opening, regex)
        self.assertIsNone(testlabels.pattern_for("a/x.rs", patterns))

    def test_overrides_merge_and_an_invalid_regex_names_the_key(self):
        # verifies: SPEC-0019/AC-01
        merged = parse(Path("."), CONFIG + '[trace.test_patterns]\n"**/*.rs" = \'^#\\[test\\]\'\n"**/*.go" = ""\n')["trace"]["test_patterns"]
        self.assertIn("**/*.py", merged)
        self.assertEqual(merged["**/*.rs"], "^#\\[test\\]")
        self.assertIsNone(testlabels.pattern_for("a/x_test.go", merged))  # "" disables a language
        with self.assertRaises(MthError) as ctx:
            parse(Path("."), CONFIG + '[trace.test_patterns]\n"**/*.py" = "("\n')
        self.assertIn("trace.test_patterns", ctx.exception.message)
        self.assertIn("**/*.py", ctx.exception.message)


class LabelTests(unittest.TestCase):
    def test_an_unlabelled_test_is_an_error_with_file_and_line(self):
        # verifies: SPEC-0019/AC-02
        text = lines("class T:", "    def test_a(self):", "        pass", "", "    def test_b(self):", "        pass")
        found = label_findings({"tests/test_x.py": text})
        self.assertEqual(len(found), 2)
        self.assertRegex(found[0], r"^tests/test_x\.py:2: test sin etiqueta")
        self.assertRegex(found[1], r"^tests/test_x\.py:5: ")

    def test_an_unlabelled_javascript_test_is_an_error_with_file_and_line(self):
        # verifies: SPEC-0019/AC-02
        text = lines("describe('x', () => {", "  it('does', () => {", "  });", "});")
        found = label_findings({"tests/x.test.ts": text})
        self.assertEqual(len(found), 1)
        self.assertRegex(found[0], r"^tests/x\.test\.ts:2: test sin etiqueta")

    def test_each_label_kind_is_accepted_in_the_region(self):
        # verifies: SPEC-0019/AC-03
        text = lines(
            "# verifies: @@/AC-01", "def test_a():", "    pass", "",
            "def test_b():", "    # verifies: @@/FM-01", "    pass", "",
            "@decorated", "# regression: #12", "def test_c():", "    pass", "",
            "def test_d():", '    """unit: parse_title"""', "    pass")
        spec = SPEC + fx("\n## Modos de fallo\n| ID | Causa | Respuesta | Cubierto por |\n|---|---|---|---|\n| FM-01 | x | y | AC-01 |\n")
        self.assertEqual(label_findings({"tests/test_x.py": text, "specs/features/a.md": spec}), [])
        # the label belongs to the test it sits in, not to its neighbour
        two = lines("def test_a():", "    # unit: a", "    pass", "", "def test_b():", "    pass")
        self.assertEqual(len(label_findings({"tests/test_x.py": two})), 1)

    def test_a_malformed_label_does_not_count_and_is_named(self):
        # verifies: SPEC-0019/AC-04
        text = lines("def test_a():", "    # verifies: pendiente", "    pass", "", "def test_b():", "    # regression:", "    pass")
        found = label_findings({"tests/test_x.py": text})
        self.assertEqual(len(found), 2)
        self.assertIn("etiqueta mal formada «verifies: pendiente»", found[0])
        self.assertIn("etiqueta mal formada «regression:»", found[1])

    def test_a_label_with_a_malformed_reference_is_named(self):
        # verifies: SPEC-0019/AC-04
        text = lines("def test_a():", "    # verifies: @@/AC-1", "    pass", "", "def test_b():", "    # unit:", "    pass")
        found = label_findings({"tests/test_x.py": text})
        self.assertEqual(len(found), 2)
        self.assertIn(fx("etiqueta mal formada «verifies: @@/AC-1»"), found[0])
        self.assertIn("etiqueta mal formada «unit:»", found[1])

    def test_a_file_without_a_pattern_needs_one_label(self):
        # verifies: SPEC-0019/AC-05
        bare = lines("#[test]", "fn works() {}")
        found = label_findings({"tests/lib_test.rs": bare})
        self.assertEqual(len(found), 1)
        self.assertRegex(found[0], r"^tests/lib_test\.rs:1: fichero de tests sin ninguna etiqueta")
        labelled = lines("// unit: parse", "#[test]", "fn works() {}")
        self.assertEqual(label_findings({"tests/lib_test.rs": labelled}), [])
        # data and helper files are not tests
        self.assertEqual(label_findings({"tests/fixture.json": "{}", "tests/helpers.rs": "fn x() {}", "tests/test_notes.md": "x"}), [])

    def test_the_configured_pattern_replaces_the_file_check(self):
        # verifies: SPEC-0019/AC-05
        config = CONFIG + '[trace.test_patterns]\n"**/*.rs" = \'^#\\[test\\]\'\n'
        text = lines("// unit: a", "#[test]", "fn a() {}", "", "#[test]", "fn b() {}")
        self.assertEqual(len(label_findings({"tests/lib_test.rs": text}, config)), 1)

    def test_legacy_files_only_warn(self):
        # verifies: SPEC-0019/AC-06
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        test_mth._write(root / "tests/test_old.py", lines("def test_a():", "    pass"))
        test_mth._write(root / "tests/test_new.py", lines("def test_b():", "    pass"))
        cfg = parse(root, CONFIG + f'[trace]\nlegacy_base = "{"a" * 40}"\n')
        ctx = SimpleNamespace(cfg=cfg, git=SimpleNamespace(files=lambda: ["tests/test_old.py", "tests/test_new.py"],
                                                          unchanged_since=lambda base: {"tests/test_old.py"}, **no_limits(root)))
        errors, legacy = flow.run_trace(ctx)
        self.assertEqual([f.path for f in errors], ["tests/test_new.py"])
        self.assertEqual([f.path for f in legacy], ["tests/test_old.py"])

    def test_a_legacy_file_without_a_pattern_only_warns(self):
        # verifies: SPEC-0019/AC-06
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        test_mth._write(root / "tests/lib_test.rs", lines("#[test]", "fn works() {}"))
        cfg = parse(root, CONFIG + f'[trace]\nlegacy_base = "{"a" * 40}"\n')
        ctx = SimpleNamespace(cfg=cfg, git=SimpleNamespace(files=lambda: ["tests/lib_test.rs"],
                                                          unchanged_since=lambda base: {"tests/lib_test.rs"}, **no_limits(root)))
        errors, legacy = flow.run_trace(ctx)
        self.assertEqual(errors, [])
        self.assertEqual([f.path for f in legacy], ["tests/lib_test.rs"])

    def test_integrate_accepts_a_labelled_new_test(self):
        # verifies: SPEC-0019/AC-07
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        test_mth._write(root / "tests/test_new.py", lines("def test_b():", "    # unit: parse", "    pass"))
        ctx = SimpleNamespace(cfg=parse(root, CONFIG), git=SimpleNamespace(files=lambda: ["tests/test_new.py"],
                                                                         unchanged_since=lambda base: set(), **no_limits(root)))
        flow._gate_trace(ctx)

    def test_integrate_rejects_an_unlabelled_test_before_touching_the_remote(self):
        # verifies: SPEC-0019/AC-07
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        test_mth._write(root / "tests/test_new.py", lines("def test_b():", "    pass"))
        ctx = SimpleNamespace(cfg=parse(root, CONFIG), git=SimpleNamespace(files=lambda: ["tests/test_new.py"],
                                                                         unchanged_since=lambda base: set(), **no_limits(root)))
        with self.assertRaises(MthError) as raised:
            flow._gate_trace(ctx)
        self.assertIn("Trazabilidad rota", raised.exception.message)
        self.assertIn("test sin etiqueta", raised.exception.message)


class SingleTestTests(unittest.TestCase):
    def test_only_criteria_with_exactly_one_test_are_warned_and_never_fail(self):
        # verifies: SPEC-0019/AC-08
        text = lines("def test_a():", "    # verifies: @@/AC-01", "    pass", "",
                     "def test_b():", "    # verifies: @@/AC-01", "    pass", "",
                     "def test_c():", "    # verifies: @@/AC-02", "    pass")
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        test_mth._write(root / "specs/features/a.md", SPEC)
        test_mth._write(root / "tests/test_x.py", text)
        names = ["specs/features/a.md", "tests/test_x.py"]
        cfg = parse(root, CONFIG)
        warned = trace.Tracer(cfg, names).single_test()
        self.assertEqual([str(f) for f in warned], [fx("specs/features/a.md:4: @@/AC-02 tiene un único test")])
        self.assertEqual(trace.check(cfg, names), [])  # a warning, not a finding


class SingleTestCliTests(RepoTestCase):
    def test_the_command_warns_lists_on_request_and_exits_zero(self):
        # verifies: SPEC-0019/AC-08
        self.write("tests/test_one.py", lines("def test_a():", f"    # verifies: {SPEC_ID}/AC-01", "    pass"))
        self.write("tests/test_two.py", lines("def test_b():", f"    # verifies: {SPEC_ID}/AC-02", "    pass", "",
                                              "def test_c():", f"    # verifies: {SPEC_ID}/AC-02", "    pass"))
        self.git("add", "-A")
        quiet = self.mth("trace")
        self.assertIn("criterios con un único test: mth trace --single los lista", quiet)
        self.assertNotIn("tiene un único test", quiet)
        listed = self.mth("trace", "--single")
        self.assertIn(f"{SPEC_ID}/AC-01 tiene un único test", listed)
        self.assertNotIn(f"{SPEC_ID}/AC-02 tiene un único test", listed)


class DanglingAndSkippedTests(unittest.TestCase):
    def test_a_label_naming_a_missing_failure_mode_is_reported(self):
        # verifies: SPEC-0019/FM-05
        # verifies: SPEC-0019/AC-03
        text = lines("def test_a():", "    # verifies: @@/FM-99", "    pass")
        found = [str(f) for f in findings({"tests/test_x.py": text, "specs/features/a.md": SPEC})]
        self.assertTrue(any(fx("referencia a @@/FM-99, que la spec no define") in f for f in found), found)

    def test_an_oversized_test_file_is_not_checked(self):
        # verifies: SPEC-0019/FM-07
        text = lines("def test_a():", "    pass") + "#" * (1_000_001)
        self.assertEqual(label_findings({"tests/test_big.py": text}), [])


class DocumentationTests(unittest.TestCase):
    def test_principles_cycle_reviewers_and_evals_cover_the_practice(self):
        # verifies: SPEC-0019/AC-09
        plugin = HERE.parent / "plugins" / "methodology"

        def read(rel: str) -> str:
            return (plugin / rel).read_text(encoding="utf-8")

        self.assertIn("Triangulación", read("PRINCIPLES.md"))
        self.assertIn("dos ejemplos de clases de equivalencia distintas", read("PRINCIPLES.md"))
        self.assertIn("Andamiaje fuera", read("PRINCIPLES.md"))
        self.assertIn("triangulación y etiqueta", read("skills/mth-develop/SKILL.md"))
        self.assertIn("Primer ejemplo en rojo", read("skills/mth-develop/SKILL.md"))
        self.assertIn("misma clase de equivalencia", read("catalog/revisor-parsimonia/agent.md.tmpl"))
        self.assertIn("**bloqueante**", read("catalog/revisor-fallos/agent.md.tmpl").split("Casos especiales", 1)[1])
        for agent, case in (("revisor-fallos", "solucion-fija-para-los-valores-del-test"),
                            ("revisor-parsimonia", "dos-tests-de-la-misma-clase")):
            self.assertIn(f'name = "{case}"', read(f"catalog/{agent}/evals.toml"))


class RepositoryTests(unittest.TestCase):
    def test_the_plugin_tests_are_labelled(self):
        # verifies: SPEC-0019/AC-10
        root = HERE.parent
        cfg = parse(root, (root / ".claude" / "methodology.toml").read_text(encoding="utf-8"))
        names = [str(p.relative_to(root)) for p in (root / "tests").glob("*.py")]
        self.assertEqual([str(f) for f in trace.Tracer(cfg, names)._test_labels(
            {n: (root / n).read_text(encoding="utf-8") for n in names if n != "tests/test_mth.py"})], [])


if __name__ == "__main__":
    unittest.main()
