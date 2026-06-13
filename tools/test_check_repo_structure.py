#!/usr/bin/env python3
"""Stdlib-only tests for check_repo_structure.py (run: python3 -m unittest)."""
import os
import tempfile
import unittest

import check_repo_structure as c

POLICY = """\
allowed_root_files:
  - "README.md"
  - "LICENSE"
  - ".gitignore"
allowed_root_dirs:
  - "src"
  - ".github"
forbidden_root_patterns:
  - '.*_(AUDIT|REVIEW|SESSION)_.*\\.md$'
  - '.*_\\d{4}-\\d{2}-\\d{2}.*\\.md$'
  - '^(TODO|ROADMAP|BACKLOG).*\\.md$'
required_files:
  - "README.md"
  - "LICENSE"
"""


def make_repo(entries):
    """entries: dict name -> True(dir) | str(file contents)."""
    root = tempfile.mkdtemp()
    for name, val in entries.items():
        path = os.path.join(root, name)
        if val is True:
            os.makedirs(path)
        else:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(val if isinstance(val, str) else "")
    return root


class ParsePolicyTests(unittest.TestCase):
    def test_parses_lists_and_keeps_single_backslash_regex(self):
        p = c.parse_policy(POLICY, "test")
        self.assertIn("README.md", p.allowed_root_files)
        self.assertIn("src", p.allowed_root_dirs)
        self.assertEqual(p.required_files, ["README.md", "LICENSE"])
        # backslash must be literal-single so \d means digit-class
        self.assertIn(r".*_\d{4}-\d{2}-\d{2}.*\.md$", p.forbidden_root_patterns)

    def test_unknown_key_is_error(self):
        with self.assertRaises(ValueError):
            c.parse_policy("allowed_root_file:\n  - x\n", "test")

    def test_bad_regex_is_error(self):
        with self.assertRaises(ValueError):
            c.parse_policy("forbidden_root_patterns:\n  - '([unclosed'\n", "test")

    def test_inline_flow_list(self):
        p = c.parse_policy('allowed_root_files: ["a", "b"]\n', "test")
        self.assertEqual(p.allowed_root_files, {"a", "b"})


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.policy = c.parse_policy(POLICY, "test")

    def test_clean_root_passes(self):
        root = make_repo({"README.md": "", "LICENSE": "", ".gitignore": "", "src": True})
        self.assertEqual(c.check(root, self.policy), [])

    def test_forbidden_dated_doc_fails(self):
        root = make_repo({"README.md": "", "LICENSE": "", "X_AUDIT_2026-06-13.md": ""})
        viol = c.check(root, self.policy)
        self.assertTrue(any("FORBIDDEN" in v for v in viol))

    def test_todo_fails(self):
        root = make_repo({"README.md": "", "LICENSE": "", "TODO.md": ""})
        viol = c.check(root, self.policy)
        self.assertTrue(any("FORBIDDEN" in v and "TODO" in v for v in viol))

    def test_disallowed_file_fails(self):
        root = make_repo({"README.md": "", "LICENSE": "", "stray.txt": ""})
        viol = c.check(root, self.policy)
        self.assertTrue(any("DISALLOWED FILE" in v for v in viol))

    def test_disallowed_dir_fails(self):
        root = make_repo({"README.md": "", "LICENSE": "", "weird": True})
        viol = c.check(root, self.policy)
        self.assertTrue(any("DISALLOWED DIR" in v for v in viol))

    def test_missing_required_fails(self):
        root = make_repo({"README.md": "", ".gitignore": ""})  # no LICENSE
        viol = c.check(root, self.policy)
        self.assertTrue(any("MISSING REQUIRED" in v for v in viol))

    def test_git_dir_ignored(self):
        root = make_repo({"README.md": "", "LICENSE": "", ".git": True})
        self.assertEqual(c.check(root, self.policy), [])

    def test_fix_only_moves_forbidden_files_not_dirs(self):
        root = make_repo(
            {"README.md": "", "LICENSE": "", "TODO.md": "", "weird": True, "stray.txt": ""}
        )
        moves = c.suggest_fixes(root, self.policy)
        names = [os.path.basename(s) for s, _ in moves]
        self.assertEqual(names, ["TODO.md"])  # not weird/ (dir), not stray.txt (not forbidden)


if __name__ == "__main__":
    unittest.main()
