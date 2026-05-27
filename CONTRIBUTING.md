# Contributing

Thanks for contributing to a Rollingcat-Software project.

## Branching & PRs
- Branch from the repository's default branch and open a pull request back into it.
  - **FIVUCSAS** (umbrella): default branch is **`master`** — target `master`.
  - **All other repos** (identity-core-api, biometric-processor, spoof-detector,
    web-app, client-apps, docs, practice-and-test): default branch is **`main`**.
- Keep PRs focused; describe the change and link any related issue.
- At least one review is required before merge; CI must be green.

## Commit messages
Use [Conventional Commits](https://www.conventionalcommits.org/):
`feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `refactor:`, `test:`, `perf:`, `build:`
(with an optional scope, e.g. `fix(auth): ...`).

## Code style & tests
- Match the surrounding code; run the repo's linter/formatter and tests locally.
- Add or update tests for behavior changes. Don't commit secrets, build output, or large binaries.

## Reporting issues
Use the issue templates. For security problems, **do not** open an issue — see
[SECURITY.md](SECURITY.md).
