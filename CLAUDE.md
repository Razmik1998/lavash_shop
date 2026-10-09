# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A LAN-only, offline-capable retail platform with two **independently
deployable** apps that share no code:

- `apps/admin/` — desktop app, PostgreSQL system of record, also runs a
  background TCP server so POS terminals can authenticate against it.
- `apps/pos/` — POS terminal desktop app. Currently has no local
  database of its own (despite the top-level README's long-term plan
  for local SQLite + sync) — today it only talks to Admin over TCP for
  login. Its `pyproject.toml`/`requirements.txt` do not depend on
  SQLAlchemy; don't assume `apps/pos/src/db.py` or a POS `migrations/`
  directory exist until that work actually lands.

There is no shared root `pyproject.toml` or root `src/` — each app
under `apps/` is set up, run, tested, and linted independently, from
inside its own directory.

## Engineering standards live under `.claude/`

This codebase is built and maintained by specialist Claude Code agents
whose contracts live in `.claude/`:

- `.claude/rules/*.md` — **non-negotiable**, override everything else
  (architecture, python, database, networking, desktop, ui-components,
  security). Read these before making structural changes; they are
  enforced by the reviewer agents.
- `.claude/skills/` — the detailed skill docs the rules point back to
  (`python-architecture`, `python-core`, `database`, `networking`,
  `desktop`, `testing`, `packaging`, `code-review`).
- `.claude/agents/*.md` — specialist agent definitions (`python-architect`,
  `python-database-engineer`, `python-desktop-engineer`,
  `python-network-engineer`, `python-engineer`, `implementer`,
  `python-test-engineer`, `python-reviewer`, `python-security-reviewer`,
  `python-performance-engineer`).
- `.claude/tasks/*.md` — canonical step-by-step procedures for common
  jobs (add a DB model, add a migration, add a LAN service, add a UI
  screen, implement a feature, write tests, review code, release).
- `.claude/workflows/*.md` — pipeline shapes (`feature-development`,
  `bug-fix`, `architecture-change`, `release`) that the tasks/commands
  follow.
- `.claude/specs/<n>/` — one directory per spec task, each with
  `input/` (the source request) and `task-plan.md` (the authoritative,
  agent-pipeline plan for that task).
- `.claude/commands/run-task.md` (invoked as `/run-task <n>`) — runs
  `.claude/specs/<n>/task-plan.md` end-to-end through its listed agents
  in order (architect/specialists → implementer → test-engineer →
  reviewer[s]), then checks off the plan's deliverables. This is the
  expected way to execute a spec task, not ad hoc implementation.

When doing any non-trivial work in this repo, read the relevant rule
file(s) and, if a spec task already exists for the work, use
`/run-task` rather than improvising the pipeline.

`docs/architecture/` and `docs/specifications/` are referenced by the
README but do not exist yet — don't assume they're there.

## Commands (run from inside `apps/admin/` or `apps/pos/`)

```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # or: pip install -r requirements.txt
cp .env.example .env
```

- Run the app: `python src/main.py`
- Lint: `ruff check .`
- Type-check: `mypy .` (strict mode is on, `mypy_path = "src"`)
- Test: `pytest` (testpaths is `tests`, `pythonpath` is `src` — no
  `src.` prefix on imports, and no path hacks needed to run a single
  file/test, e.g. `pytest tests/unit/test_services.py::test_name`)
- Migrations (`apps/admin` only — Postgres, via Alembic against
  `migrations/`): `alembic revision --autogenerate -m "..."` then
  **manually review** the generated migration before `alembic upgrade
  head`, per `.claude/rules/database.md`. `apps/pos` has no migrations
  directory yet.

Both apps' `.env.example` define the LAN contact point:
`DATABASE_URL`/`ADMIN_LAN_PORT` (admin) and `ADMIN_HOST`/`ADMIN_PORT`
(pos), matching on port 8765 by default.

## Architecture (per app)

Each app follows the same layering, enforced file-by-file:

```
ui/*.py          → services/ → repositories/ / networking/* → models/
(presentation)      (application)  (infrastructure)                (domain)
```

- `models/` — SQLAlchemy models and enums grouped by feature. No behavior
  beyond the data shape; `models/__init__.py` preserves flat imports.
- `services/` — the only layer the UI is allowed to call into. Services are
  grouped by feature; `services/__init__.py` preserves flat imports.
  Constructs domain objects, applies business rules (e.g. `ProductService`
  computing `stock_status`/`profit_margin`), and raises the app's
  domain exceptions (`exceptions.py`, e.g. `AuthenticationError`,
  `SkuAlreadyExistsError`).
- `repositories/` (admin only) — the *only* package besides `db.py`
  allowed to import `sqlalchemy` or hold a `Session`/`sessionmaker`.
  `repository.py` is a compatibility shim for legacy imports.
  Translates `IntegrityError` into domain exceptions (e.g. duplicate
  SKU/barcode/username) rather than leaking SQLAlchemy errors upward.
- `schemas/` — service-facing dataclasses and value objects grouped by
  feature. Schemas do not import UI or repositories.
- `db.py` (admin only) — builds the engine/session factory from
  `Settings`.
- `config.py` — `Settings` dataclass loaded from environment/`.env` via
  `python-dotenv`; raises `RuntimeError` if required vars are missing.
  No secrets in source.
- `networking/` — the LAN boundary, kept intentionally separate per
  app rather than shared:
  - `apps/admin/src/networking/protocol.py` + `server.py`: a daemon
    `ThreadingTCPServer` started from `main.py`, one newline-delimited
    JSON object per request/response, one short-lived TCP connection
    per request. Delegates all auth to `AuthService`; never touches
    SQL directly.
  - `apps/pos/src/networking/connection.py`: an `AdminConnection` ABC —
    `services.py`/UI depend on this abstraction only, never on
    `socket`/`json` directly.
  - `apps/pos/src/networking/local_connection.py`: the current
    loopback-only `AdminConnection` implementation, with a connect
    timeout, read timeout, and single retry before raising
    `AdminUnavailableError`. **Documented trust-model exception**: it
    sends the login request (which carries the password) without TLS,
    justified only because traffic stays on loopback. A future
    cross-machine `LanConnection` must not reuse that exception and
    must add TLS (see the module docstrings and `.claude/rules/security.md`).
  - Both protocol modules deliberately never log raw request/response
    bodies (they carry the password) — only operation + outcome.
- `ui/*.py` — PySide6 widgets/windows. Must not hold SQL, sockets, or
  business rules; calls into `services.py` only.
  `ui/components/` is each app's component library and the **only**
  source of styled widgets: `buttons.py` (`AppButton` + semantic
  subclasses — `PrimaryButton`, `SaveButton`, `EditButton` (yellow),
  `DeleteButton`/`CancelButton`/`CloseButton` (red), `PaymentButton`,
  ...), `inputs.py` (`TextField`, `SearchField`, `MoneyField`,
  `QuantityField`, `SelectField`, `DateField`), `tables.py`
  (`DataTable`, `SimpleTable`), `panels.py` (`Panel`, `PageTitle`,
  `PageSubtitle`, `StatusBadge`, `StatCard`), `layouts.py`
  (`ActionBar`, `FilterBar`, `DialogButtonBar`, `Toolbar`) and
  `feedback.py` (`confirm`/`warn`/`inform`/`report_error`). Screens
  never construct `QPushButton`/`QTableView`/`QLineEdit`/`QMessageBox`
  directly and never call `setObjectName`/`setStyleSheet`; if a shape is
  needed twice it becomes a component first (see
  `.claude/rules/ui-components.md`). `ui/style.py` owns the stylesheet,
  `configure_table_view`, and the `format_currency`/`format_quantity`
  number formatters that every rendered number must go through.
  `ui/workers.py` provides `run_in_background()`, a `QThread`-subclass
  helper (overrides `run()` directly rather than
  `moveToThread()`/`quit()`) so DB/network calls in service methods
  never block the Qt event loop; results are delivered back to the UI
  thread via queued signals. `wait_for_pending_threads()` is the one
  sanctioned bounded blocking `QThread.wait()`, called from a widget's
  `closeEvent`.
- `main.py` — wires everything together (config → db/connection →
  repositories/connection → services → background TCP server (admin
  only) → `QApplication` → login window → main/home window) and owns
  process lifecycle (e.g. shutting down the TCP server on
  `aboutToQuit`).

Tests mirror this layering under `tests/unit/`, `tests/integration/`
(admin: real-DB repository tests via `conftest.py`), and `tests/gui/`
(pytest-qt).
