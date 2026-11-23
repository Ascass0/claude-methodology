"""Tests of the read-only SQLite queries of lector-estado (SPEC-0012)."""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

import catalog_support  # noqa: F401 — puts mthlib on sys.path
import test_mth
from mthlib import cli, db_query

ROWS = 5


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        con = sqlite3.connect(self.root / "state.db")
        con.executescript("CREATE TABLE t(a, b); " + " ".join(f"INSERT INTO t VALUES ({i}, 'x{i}');" for i in range(ROWS)))
        con.close()
        self.dbs = {"estado": "state.db"}

    def query(self, sql, alias="estado", max_rows=100, timeout_s=10):
        return db_query.query(self.dbs, self.root, alias, sql, max_rows=max_rows, timeout_s=timeout_s)

    def count(self) -> int:
        return sqlite3.connect(self.root / "state.db").execute("SELECT count(*) FROM t").fetchone()[0]

    def test_rejects_writes_attach_multiple_statements_and_extensions(self):
        # verifies: SPEC-0012/AC-11
        bad = ["INSERT INTO t VALUES (9, 'y')", "UPDATE t SET a = 0", "DELETE FROM t", "DROP TABLE t",
               f"ATTACH DATABASE '{self.root / 'x.db'}' AS x", "PRAGMA writable_schema = 1",
               "PRAGMA query_only = OFF", "SELECT 1; DELETE FROM t", "SELECT load_extension('x')",
               "CREATE TEMP TABLE z(a)", "VACUUM", "SELECT writefile('x', 'y')"]
        for sql in bad:
            with self.subTest(sql=sql), self.assertRaises(db_query.QueryError):
                self.query(sql)
        self.assertEqual(self.count(), ROWS)
        self.assertFalse((self.root / "x.db").exists())

    def test_reads_schema_and_pragma_info(self):
        self.assertEqual(self.query(None).columns, ["name", "sql"])
        self.assertEqual(len(self.query("PRAGMA table_info(t)").rows), 2)

    def test_rejects_undeclared_aliases_and_caps_rows(self):
        # verifies: SPEC-0012/AC-12
        with self.assertRaises(db_query.QueryError) as ctx:
            self.query("SELECT 1", alias="otra")
        self.assertIn("estado", ctx.exception.message)
        result = self.query("SELECT a FROM t ORDER BY a", max_rows=2)
        self.assertEqual(result, db_query.Result(["a"], [(0,), (1,)], True))
        self.assertFalse(self.query("SELECT a FROM t", max_rows=ROWS).truncated)
        self.assertIn("truncado a 2 filas", db_query.format_result(result, 2))

    def test_slow_queries_are_cut(self):
        slow = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT count(*) FROM n"
        with self.assertRaises(db_query.QueryError) as ctx:
            self.query(slow, timeout_s=0.2)
        self.assertIn("límite", ctx.exception.message)

    def test_missing_database_file(self):
        self.dbs["vacia"] = "no-existe.db"
        with self.assertRaises(db_query.QueryError):
            self.query("SELECT 1", alias="vacia")

    def test_rejects_paths_outside_the_repository_and_non_positive_limits(self):
        # verifies: SPEC-0012/AC-26
        outside = self.root.parent / f"{self.root.name}-fuera.db"
        sqlite3.connect(outside).close()
        self.addCleanup(outside.unlink)
        (self.root / "enlace.db").symlink_to(outside)
        for alias, path in {"rel": f"../{outside.name}", "abs": str(outside), "enlace": "enlace.db"}.items():
            self.dbs[alias] = path
            with self.subTest(alias=alias), self.assertRaises(db_query.QueryError) as ctx:
                self.query("SELECT 1", alias=alias)
            self.assertIn("fuera del repositorio", ctx.exception.message)
        for limits in ({"max_rows": 0}, {"timeout_s": 0}, {"max_rows": -1}):
            with self.subTest(limits=limits), self.assertRaises(db_query.QueryError):
                self.query("SELECT 1", **limits)

    def test_values_and_cells_are_bounded(self):
        # verifies: SPEC-0012/AC-26
        with self.assertRaises(db_query.QueryError):
            self.query(f"SELECT zeroblob({db_query.MAX_VALUE_BYTES + 1})")
        long = self.query("SELECT printf('%.*c', 5000, 'x')")
        text = db_query.format_result(long, 10).splitlines()[1]
        self.assertLess(len(text), db_query.MAX_CELL_CHARS + 50)
        self.assertIn("caracteres más", text)

    def test_cells_are_escaped(self):
        result = db_query.Result(["a"], [("x\ty\nz",), (None,), (b"\x00\x01",)], False)
        self.assertEqual(db_query.format_result(result, 10), "a\nx\\ty\\nz\nNULL\n<2 bytes>")


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True, env={**os.environ, **test_mth.GIT_ENV})
        test_mth._write(self.root / ".claude/methodology.toml", """
            version = 1
            [commands]
            test = ""
            [agents.lector-estado]
            databases = { estado = "data/state.db" }
            max_rows = 3
            """)
        (self.root / "data").mkdir()
        con = sqlite3.connect(self.root / "data/state.db")
        con.executescript("CREATE TABLE t(a); " + " ".join(f"INSERT INTO t VALUES ({i});" for i in range(10)))
        con.close()
        self.cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.cwd)

    def mth(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def test_uses_the_configured_row_limit(self):
        # verifies: SPEC-0012/AC-12
        rc, out, _ = self.mth("db-query", "--db", "estado", "SELECT a FROM t ORDER BY a")
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines()[:4], ["a", "0", "1", "2"])
        self.assertIn("truncado a 3 filas", out)

    def test_errors_are_reported_without_touching_the_database(self):
        # verifies: SPEC-0012/AC-11
        rc, _, err = self.mth("db-query", "--db", "estado", "DELETE FROM t")
        self.assertEqual(rc, 1)
        self.assertIn("rechazada", err)
        rc, _, err = self.mth("db-query", "--db", "otra", "--schema")
        self.assertEqual(rc, 1)
        self.assertEqual(sqlite3.connect(self.root / "data/state.db").execute("SELECT count(*) FROM t").fetchone()[0], 10)

    def test_schema_and_sql_are_exclusive(self):
        rc, _, err = self.mth("db-query", "--db", "estado", "--schema", "SELECT 1")
        self.assertEqual(rc, 1)
        rc, out, _ = self.mth("db-query", "--db", "estado", "--schema")
        self.assertEqual((rc, out.splitlines()[0]), (0, "name\tsql"))


if __name__ == "__main__":
    unittest.main()
