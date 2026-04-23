#!/usr/bin/env python3
"""Tests for the justfile recipe extractor used by jolo migrate-justfile."""

import unittest

from _jolo.justfile_parser import (
    extract_recipes,
    has_import,
    insert_import,
    remove_recipes,
)


class TestExtractRecipes(unittest.TestCase):
    """Locate top-level recipe definitions by name."""

    def test_simple_recipe(self):
        src = "perf:\n    echo hi\n"
        got = extract_recipes(src, {"perf"})
        self.assertEqual(len(got), 1)
        self.assertEqual(got["perf"].strip(), "perf:\n    echo hi")

    def test_recipe_with_params(self):
        src = "a11y *args:\n    pa11y {{args}}\n"
        got = extract_recipes(src, {"a11y"})
        self.assertIn("a11y", got)
        self.assertIn("*args", got["a11y"])

    def test_recipe_with_default_arg(self):
        src = 'db *args="start":\n    db {{args}}\n'
        got = extract_recipes(src, {"db"})
        self.assertIn("db", got)
        self.assertIn('*args="start"', got["db"])

    def test_multi_line_body_with_shebang(self):
        src = (
            "perf:\n"
            "    #!/bin/sh\n"
            "    set -eu\n"
            "    echo 1\n"
            "    echo 2\n"
            "other:\n"
            "    echo other\n"
        )
        got = extract_recipes(src, {"perf"})
        self.assertIn("perf", got)
        body = got["perf"]
        self.assertIn("#!/bin/sh", body)
        self.assertIn("set -eu", body)
        self.assertIn("echo 2", body)
        self.assertNotIn("echo other", body)

    def test_body_ends_at_next_recipe_header(self):
        src = "a:\n    echo a\nb:\n    echo b\n"
        got = extract_recipes(src, {"a"})
        self.assertEqual(got["a"].strip(), "a:\n    echo a")

    def test_includes_preceding_comments(self):
        """Doc comments on the lines just above a recipe belong to it."""
        src = "# Open in browser\nbrowse:\n    chromium\n"
        got = extract_recipes(src, {"browse"})
        self.assertIn("# Open in browser", got["browse"])

    def test_blank_line_breaks_comment_group(self):
        """A blank between a stray comment and the recipe doesn't adopt it."""
        src = "# stray top-of-file comment\n\nperf:\n    echo hi\n"
        got = extract_recipes(src, {"perf"})
        self.assertNotIn("stray top-of-file", got["perf"])

    def test_attribute_line_included(self):
        src = "[private]\nsetup:\n    echo hi\n"
        got = extract_recipes(src, {"setup"})
        self.assertIn("[private]", got["setup"])

    def test_only_top_level_headers_match(self):
        """Indented 'perf:' inside another recipe body is NOT a recipe."""
        src = "other:\n    echo perf:\n    echo done\n"
        got = extract_recipes(src, {"perf"})
        self.assertEqual(got, {})

    def test_settings_lines_are_not_recipes(self):
        """`set shell := ...` and `export FOO := ...` are settings, not recipes."""
        src = 'set shell := ["bash"]\nexport FOO := "1"\nperf:\n    echo hi\n'
        got = extract_recipes(src, {"perf", "set", "export"})
        self.assertIn("perf", got)
        self.assertNotIn("set", got)
        self.assertNotIn("export", got)

    def test_absent_recipe_not_in_result(self):
        src = "perf:\n    echo hi\n"
        got = extract_recipes(src, {"browse"})
        self.assertEqual(got, {})

    def test_empty_source(self):
        self.assertEqual(extract_recipes("", {"perf"}), {})


class TestRemoveRecipes(unittest.TestCase):
    """Remove named recipes from a justfile, leaving the rest intact."""

    def test_removes_one(self):
        src = "perf:\n    echo hi\nother:\n    echo other\n"
        got = remove_recipes(src, {"perf"})
        self.assertNotIn("perf:", got)
        self.assertIn("other:", got)

    def test_removes_all_specified(self):
        src = "a:\n    echo a\nb:\n    echo b\nc:\n    echo c\n"
        got = remove_recipes(src, {"a", "b"})
        self.assertNotIn("\na:", "\n" + got)
        self.assertNotIn("\nb:", "\n" + got)
        self.assertIn("c:", got)

    def test_preserves_multi_line_body(self):
        src = "user:\n    echo 1\n    echo 2\nperf:\n    echo perf\n"
        got = remove_recipes(src, {"perf"})
        self.assertIn("user:", got)
        self.assertIn("echo 2", got)
        self.assertNotIn("perf:", got)
        self.assertNotIn("echo perf", got)

    def test_removes_leading_doc_comment_with_recipe(self):
        src = "user:\n    echo u\n\n# Open in browser\nbrowse:\n    chromium\n"
        got = remove_recipes(src, {"browse"})
        self.assertIn("user:", got)
        self.assertNotIn("browse:", got)
        self.assertNotIn("Open in browser", got)

    def test_nothing_to_remove(self):
        src = "user:\n    echo u\n"
        self.assertEqual(remove_recipes(src, {"perf"}), src)

    def test_preserves_settings_and_imports(self):
        src = (
            'set shell := ["bash"]\n'
            "\n"
            "perf:\n    echo hi\n"
            "\n"
            "user:\n    echo u\n"
        )
        got = remove_recipes(src, {"perf"})
        self.assertIn('set shell := ["bash"]', got)
        self.assertIn("user:", got)
        self.assertNotIn("perf:", got)


class TestInsertImport(unittest.TestCase):
    """Insert `import 'justfile.common'` in the right place."""

    def test_empty_input(self):
        self.assertEqual(insert_import(""), "import 'justfile.common'\n")

    def test_prepends_for_plain_recipe_justfile(self):
        src = "dev:\n    echo dev\n"
        got = insert_import(src)
        self.assertTrue(got.startswith("import 'justfile.common'"))
        self.assertIn("dev:", got)

    def test_preserves_shebang_line(self):
        src = "#!/usr/bin/env just --justfile\n\ndev:\n    echo dev\n"
        got = insert_import(src)
        self.assertTrue(got.startswith("#!/usr/bin/env just"))
        self.assertIn("import 'justfile.common'", got)
        # Import comes before the first recipe
        self.assertLess(
            got.index("import 'justfile.common'"), got.index("dev:")
        )

    def test_placed_after_set_shell_directive(self):
        src = 'set shell := ["bash"]\n\ndev:\n    echo dev\n'
        got = insert_import(src)
        # `set shell` must precede the import so it applies to imported recipes
        self.assertLess(
            got.index("set shell"), got.index("import 'justfile.common'")
        )
        self.assertLess(
            got.index("import 'justfile.common'"), got.index("dev:")
        )

    def test_placed_after_export_directive(self):
        src = 'export FOO := "bar"\n\ndev:\n    echo dev\n'
        got = insert_import(src)
        self.assertLess(
            got.index("export FOO"),
            got.index("import 'justfile.common'"),
        )

    def test_placed_after_leading_comments(self):
        src = "# my project justfile\n# copyright me\n\ndev:\n    echo dev\n"
        got = insert_import(src)
        self.assertLess(
            got.index("my project justfile"),
            got.index("import 'justfile.common'"),
        )

    def test_idempotent_single_quotes(self):
        src = "import 'justfile.common'\n\ndev:\n    echo dev\n"
        self.assertEqual(insert_import(src), src)

    def test_idempotent_double_quotes(self):
        src = 'import "justfile.common"\n\ndev:\n    echo dev\n'
        self.assertEqual(insert_import(src), src)

    def test_idempotent_with_trailing_comment(self):
        src = "import 'justfile.common' # shared recipes\n\ndev:\n    echo d\n"
        self.assertEqual(insert_import(src), src)


class TestHasImport(unittest.TestCase):
    """Detect whether a justfile already imports justfile.common."""

    def test_present_single_quotes(self):
        self.assertTrue(has_import("import 'justfile.common'\n"))

    def test_present_double_quotes(self):
        self.assertTrue(has_import('import "justfile.common"\n'))

    def test_present_with_leading_whitespace(self):
        self.assertTrue(has_import("   import 'justfile.common'\n"))

    def test_absent(self):
        self.assertFalse(has_import("perf:\n    echo hi\n"))

    def test_different_import(self):
        self.assertFalse(has_import("import 'other.common'\n"))

    def test_present_with_trailing_comment(self):
        self.assertTrue(has_import("import 'justfile.common' # shared\n"))


if __name__ == "__main__":
    unittest.main()
