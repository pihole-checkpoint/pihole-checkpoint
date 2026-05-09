# Dependency Upgrade Report — 2026-05-09

## Summary
- Total outdated: 20 (10 direct, 10 transitive)
- Safe to upgrade: 6
- Needs code changes: 2
- Hold back: 2
- Detected ecosystems: Python (uv)

Transitive packages (asgiref, certifi, charset-normalizer, coverage, Faker,
idna, packaging, pip, Pygments, urllib3) are not directly managed; they
re-resolve via `uv lock` when their parents change.

## Safe upgrades (applied in this PR)

| Package | Kind | From | To | Notable | Source |
|---|---|---|---|---|---|
| `requests` | runtime | 2.32.5 | 2.33.1 | Security hardening; Py3.9 drop irrelevant (we require Py3.12) | [releases](https://github.com/psf/requests/releases) |
| `python-dotenv` | runtime | 1.2.1 | 1.2.2 | Read-only `load_dotenv` path unaffected by symlink/permission tweak | [v1.2.2](https://github.com/theskumar/python-dotenv/releases/tag/v1.2.2) |
| `whitenoise` | runtime | 6.11.0 | 6.12.0 | Autorefresh-mode CVE fix; production uses non-autorefresh path | [changelog](https://raw.githubusercontent.com/evansd/whitenoise/main/docs/changelog.rst) |
| `pytest` | dev | 9.0.2 | 9.0.3 | Patch + tmpdir CVE-2025-71176 fix | [9.0.3](https://github.com/pytest-dev/pytest/releases/tag/9.0.3) |
| `pytest-cov` | dev | 7.0.0 | 7.1.0 | Bug-fix only | [changelog](https://github.com/pytest-dev/pytest-cov/blob/master/CHANGELOG.rst) |
| `pytest-django` | dev | 4.11.1 | 4.12.0 | Additive: new `django_isolate_apps` marker; no DB/fixture behavior changes | [changelog](https://github.com/pytest-dev/pytest-django/blob/main/docs/changelog.rst) |

## Needs code changes (NOT applied)

### `responses` (0.25.8 → 0.26.0)
- **Required changes**: Audit `backup/tests/` for `@responses.activate` usages
  that rely on swallowed unfired-mock errors in exception paths. Either
  ensure all registered mocks fire, or pass
  `assert_all_requests_are_fired=False` where appropriate. The 0.26.0
  release tightens assertion propagation: unfired mocks now always raise,
  even when the wrapped function raises.
- **Deprecations**: none
- **Source**: https://github.com/getsentry/responses/blob/master/CHANGES

### `ruff` (0.14.13 → 0.15.12)
- **Required changes**: 0.15.0 ships the 2026 style guide which reformats
  code (lambda parameter handling, exception clause parens for Py3.14+,
  blank line rule adjustments). Selected rules `["E","F","I","W"]` gain no
  new defaults, but `ruff format --check .` will fail in CI until the
  codebase is reformatted. Plan: bump ruff in a dedicated PR, run
  `uv run ruff format .`, commit reformatted output as a single follow-up
  commit so blame stays clean.
- **Deprecations**: none affecting the selected rule set
- **Source**: https://github.com/astral-sh/ruff/releases

## Hold back

### `gunicorn` (23.0.0 → 26.0.0)
- **Why**: Three-major span (23 → 24 → 25 → 26). Skill rule: majors are
  always HOLD_BACK regardless of release-note content. Investigation found
  no operational blockers for our default sync-worker setup
  (`entrypoint.sh` uses `--workers 2`, no eventlet, no custom request-target
  shapes). Realistic risk surface is the 26.0.0 RFC 9112 HTTP/1.1
  request-target validation — only matters if a client or upstream proxy
  emits malformed request lines.
- **Suggested follow-up**: Dedicated PR with manual `entrypoint.sh` smoke
  test + a request smoke through the reverse proxy. Optionally open an ADR
  if the upgrade exposes infra coupling.
- **Source**: https://github.com/benoitc/gunicorn/releases

### `Django` (5.2.10 → 6.0.5)
- **Why**: Blocked at the pin: `Django>=5.0,<6.0` in `pyproject.toml`. A 6.x
  bump is a deliberate decision and should go through `/adr` rather than a
  dep-upgrade pass.
- **Suggested follow-up**: Open an ADR scoped to Django 6.0 readiness
  (third-party app compatibility audit, deprecation sweeps). Document the
  pin's intent inline when it's ever lifted.
- **Source**: https://docs.djangoproject.com/en/6.0/releases/6.0/

## Methodology
- Agents dispatched: 8 (in 1 wave) — 1 each for the 8 outdated direct deps
  whose target was reachable. Django was excluded because the `<6.0` pin
  makes the 6.0.5 target unreachable without a constraint change.
- Investigation failures (manual review needed): none
- Skipped ecosystems (tooling missing): none — repo is Python-only
