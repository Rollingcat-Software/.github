#!/usr/bin/env python3
"""Repo structure-lock — an ArchUnit-style FREEZE for a repository's file/folder layout.

Reads a per-repo policy (``.repo-structure.yml`` or ``.github/repo-structure.yml``)
and FAILS (exit 1) when the layout drifts from the frozen baseline:

  * a root entry that is not in the allowlist appears, OR
  * any path matches a FORBIDDEN regex pattern, OR
  * a REQUIRED file is missing.

The intent (see Rollingcat-Software/FIVUCSAS#209): dated tracking docs
(``*_AUDIT_*``, ``*_2026-06-13*``, ``TODO.md`` …) belong in GitHub issues, never
at a repo root. This gate makes the convention executable: violations block CI the
same way ArchUnit fails the build.

Stdlib-only — no PyYAML, no third-party deps. The policy file uses a deliberately
small YAML subset (top-level ``key:`` mappings whose values are block lists of
``- "string"`` items, plus ``# comments``) which this module parses directly.

Usage:
    python3 tools/check_repo_structure.py [--root DIR] [--policy FILE] [--fix]

Exit codes:
    0  layout matches the policy (clean)
    1  one or more violations
    2  usage / policy error (no policy found, malformed policy, bad args)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field

DEFAULT_POLICY_NAMES = (".repo-structure.yml", ".github/repo-structure.yml")

# Root entries that are never part of a repo's layout and must always be ignored:
#   .git                    — the git dir
#   .repo-structure-tools   — where the reusable workflow checks out THIS tooling
#                             repo into the scanned workspace (else the gate would
#                             flag its own checkout as a disallowed dir).
ALWAYS_IGNORED = frozenset({".git", ".repo-structure-tools"})

# Recognised policy keys. Anything else in the policy file is an error so typos
# (e.g. ``allowed_root_file:``) surface loudly instead of silently doing nothing.
KNOWN_KEYS = (
    "allowed_root_files",
    "allowed_root_dirs",
    "forbidden_root_patterns",
    "required_files",
)


@dataclass
class Policy:
    allowed_root_files: set[str] = field(default_factory=set)
    allowed_root_dirs: set[str] = field(default_factory=set)
    forbidden_root_patterns: list[str] = field(default_factory=list)
    required_files: list[str] = field(default_factory=list)


def _strip_inline_comment(value: str) -> str:
    """Drop an unquoted trailing ``# comment`` from a scalar value."""
    out = []
    quote = None
    for ch in value:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).strip()


def _unquote(value: str) -> str:
    """Strip a single layer of surrounding quotes; keep the inner bytes verbatim.

    NOTE: this is intentionally literal — it does NOT process YAML/JSON backslash
    escapes. Regex patterns therefore must be written with SINGLE backslashes in
    the policy (``\\d``, ``\\.``) and are best wrapped in single quotes, e.g.
    ``- '.*_\\d{4}-\\d{2}-\\d{2}.*\\.md$'``. (Double-quoting and writing ``\\\\d``
    would store a literal backslash and break the pattern.)
    """
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_policy(text: str, source: str) -> Policy:
    """Parse the small YAML subset used by ``.repo-structure.yml``.

    Supported shape (only):

        key: [list item, ...]          # inline flow list, or
        key:
          - "item"                     # block list, one item per line
          - item

    Scalars may be single/double quoted. ``#`` starts a comment. Indentation of
    list items must be deeper than their key. Anything outside this grammar is a
    policy error (exit 2) rather than a silent pass.
    """
    policy = Policy()
    current_key: str | None = None

    lines = text.splitlines()
    for lineno, raw in enumerate(lines, start=1):
        # Blank or comment-only line.
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()

        if stripped.startswith("- "):
            if current_key is None:
                raise ValueError(
                    f"{source}:{lineno}: list item with no preceding key: {raw!r}"
                )
            item = _unquote(_strip_inline_comment(stripped[2:]))
            if item:
                _append(policy, current_key, item, source, lineno)
            continue

        # Otherwise it must be a ``key:`` mapping line at column 0.
        if indent != 0:
            raise ValueError(f"{source}:{lineno}: unexpected indentation: {raw!r}")
        if ":" not in stripped:
            raise ValueError(f"{source}:{lineno}: expected 'key:' mapping: {raw!r}")

        key, _, rest = stripped.partition(":")
        key = key.strip()
        if key not in KNOWN_KEYS:
            raise ValueError(
                f"{source}:{lineno}: unknown policy key {key!r} "
                f"(expected one of {', '.join(KNOWN_KEYS)})"
            )
        current_key = key
        rest = _strip_inline_comment(rest)
        if rest:
            # Inline flow list:  key: [a, b]   or a bare scalar (rejected).
            if rest.startswith("[") and rest.endswith("]"):
                for piece in rest[1:-1].split(","):
                    item = _unquote(piece.strip())
                    if item:
                        _append(policy, key, item, source, lineno)
            else:
                raise ValueError(
                    f"{source}:{lineno}: value for {key!r} must be a list "
                    f"(use a block list or [a, b]); got {rest!r}"
                )

    return policy


def _append(policy: Policy, key: str, item: str, source: str, lineno: int) -> None:
    if key == "allowed_root_files":
        policy.allowed_root_files.add(item)
    elif key == "allowed_root_dirs":
        policy.allowed_root_dirs.add(item)
    elif key == "forbidden_root_patterns":
        try:
            re.compile(item)
        except re.error as exc:
            raise ValueError(
                f"{source}:{lineno}: invalid regex in forbidden_root_patterns: "
                f"{item!r} ({exc})"
            ) from exc
        policy.forbidden_root_patterns.append(item)
    elif key == "required_files":
        policy.required_files.append(item)


def find_policy(root: str, explicit: str | None) -> str:
    if explicit:
        path = explicit if os.path.isabs(explicit) else os.path.join(root, explicit)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"policy file not found: {explicit}")
        return path
    for name in DEFAULT_POLICY_NAMES:
        candidate = os.path.join(root, name)
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError(
        "no policy file found (looked for "
        + " and ".join(DEFAULT_POLICY_NAMES)
        + "). Add one frozen from the current clean root."
    )


def list_root_entries(root: str) -> list[tuple[str, bool]]:
    """Return ``(name, is_dir)`` for each top-level entry, minus ALWAYS_IGNORED."""
    entries = []
    for name in sorted(os.listdir(root)):
        if name in ALWAYS_IGNORED:
            continue
        is_dir = os.path.isdir(os.path.join(root, name))
        entries.append((name, is_dir))
    return entries


def check(root: str, policy: Policy) -> list[str]:
    """Return a list of human-readable violation strings (empty == clean)."""
    violations: list[str] = []
    compiled = [(p, re.compile(p)) for p in policy.forbidden_root_patterns]

    for name, is_dir in list_root_entries(root):
        # Forbidden patterns take precedence and apply to files and dirs alike.
        matched_forbidden = False
        for pattern, rx in compiled:
            if rx.search(name):
                violations.append(
                    f"FORBIDDEN: root entry {name!r} matches forbidden pattern "
                    f"/{pattern}/ — tracking docs belong in GitHub issues, not the repo root"
                )
                matched_forbidden = True
                break
        if matched_forbidden:
            continue

        if is_dir:
            if name not in policy.allowed_root_dirs:
                violations.append(
                    f"DISALLOWED DIR: {name!r} is not in allowed_root_dirs — "
                    f"if intentional, add it to .repo-structure.yml"
                )
        else:
            if name not in policy.allowed_root_files:
                violations.append(
                    f"DISALLOWED FILE: {name!r} is not in allowed_root_files — "
                    f"if intentional, add it to .repo-structure.yml"
                )

    for required in policy.required_files:
        if not os.path.isfile(os.path.join(root, required)):
            violations.append(f"MISSING REQUIRED FILE: {required!r}")

    return violations


def suggest_fixes(root: str, policy: Policy) -> list[tuple[str, str]]:
    """Return ``(src, dst)`` moves for forbidden root files into docs/archive/.

    Only suggests moves for *files* matching a forbidden pattern (never dirs,
    never disallowed-but-not-forbidden entries — those need a human decision).
    """
    moves: list[tuple[str, str]] = []
    compiled = [re.compile(p) for p in policy.forbidden_root_patterns]
    for name, is_dir in list_root_entries(root):
        if is_dir:
            continue
        if any(rx.search(name) for rx in compiled):
            moves.append(
                (
                    os.path.join(root, name),
                    os.path.join(root, "docs", "archive", name),
                )
            )
    return moves


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze and enforce a repo's root file/folder layout (FIVUCSAS#209)."
    )
    parser.add_argument(
        "--root", default=".", help="repository root to scan (default: cwd)"
    )
    parser.add_argument(
        "--policy",
        default=None,
        help="policy file path (default: .repo-structure.yml or .github/repo-structure.yml)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="MOVE forbidden root tracking-docs into docs/archive/ "
        "(convenience helper — never run automatically in CI)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with --fix, only print the moves that would be made",
    )
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"error: --root is not a directory: {root}", file=sys.stderr)
        return 2

    try:
        policy_path = find_policy(root, args.policy)
        with open(policy_path, "r", encoding="utf-8") as handle:
            policy = parse_policy(handle.read(), os.path.relpath(policy_path, root))
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.fix:
        moves = suggest_fixes(root, policy)
        if not moves:
            print("no forbidden root files to move.")
            return 0
        for src, dst in moves:
            if args.dry_run:
                print(f"would move: {os.path.relpath(src, root)} -> {os.path.relpath(dst, root)}")
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.replace(src, dst)
                print(f"moved: {os.path.relpath(src, root)} -> {os.path.relpath(dst, root)}")
        print(
            "\n--fix is a convenience helper; review the moves, then re-run the "
            "check to confirm the gate passes."
        )
        return 0

    violations = check(root, policy)
    if violations:
        print(
            f"Repo structure-lock FAILED for {root} "
            f"({len(violations)} violation(s)):\n",
            file=sys.stderr,
        )
        for item in violations:
            print(f"  - {item}", file=sys.stderr)
        print(
            "\nThe layout drifted from the frozen baseline in "
            f"{os.path.relpath(policy_path, root)}.\n"
            "Dated tracking docs (audits/reviews/sessions/TODOs) go in GitHub "
            "issues, not the repo root.\n"
            "To intentionally allow a NEW root entry, add it to the policy in the "
            "same PR (that is the explicit, reviewed unfreeze).",
            file=sys.stderr,
        )
        return 1

    print(
        f"Repo structure-lock PASSED — root layout matches "
        f"{os.path.relpath(policy_path, root)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
