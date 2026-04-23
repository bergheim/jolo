#!/usr/bin/env python3
"""Tests for _jolo.justfile_parser."""

import unittest

from _jolo.justfile_parser import has_import, insert_import


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
        self.assertLess(
            got.index("import 'justfile.common'"), got.index("dev:")
        )

    def test_placed_after_set_shell_directive(self):
        src = 'set shell := ["bash"]\n\ndev:\n    echo dev\n'
        got = insert_import(src)
        # set shell must precede the import so it applies to imported recipes
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
