# Fish Shop Monorepo

A LAN-only, offline-capable retail platform: a central **Admin** desktop
application (PostgreSQL system of record) and independently deployable
**POS** terminal applications (local SQLite, synchronized to Admin over
the LAN). See `docs/architecture/overview.md`,
`docs/architecture/technical-notes.md`, and `docs/specifications/` for
the full business and technical specification.

This project is built and maintained by a set of specialist Claude Code
agents defined under `.claude/`. See `.claude/agents/`, `.claude/skills/`,
`.claude/tasks/`, `.claude/rules/`, and `.claude/workflows/` for the
engineering standards and workflows that govern this codebase.

## Layout

```
apps/
├── admin/            Admin application (PostgreSQL system of record)
│   ├── src/
│   ├── tests/
│   ├── migrations/   Alembic migrations against PostgreSQL
│   ├── pyproject.toml
│   └── .env.example
└── pos/               POS terminal application (local SQLite + sync)
    ├── src/
    ├── tests/
    ├── migrations/    Alembic migrations against SQLite
    ├── pyproject.toml
    └── .env.example
docs/
├── architecture/      system overview and technical notes
└── specifications/    business roles, requirements, engineering notes, test plan
```

Each app under `apps/` is independently installable, configurable, and
runnable, per `docs/architecture/technical-notes.md` — there is no
shared root `pyproject.toml`/`src/`.

## Technology baseline

- Python 3.12+
- PySide6 (desktop UI, both apps)
- Admin: PostgreSQL + SQLAlchemy 2.x + psycopg + Alembic
- POS: local SQLite + SQLAlchemy 2.x + Alembic
- Argon2id for password hashing, Decimal for all money/quantity math
- pytest (+ pytest-qt for GUI), Ruff, mypy

## Setup (per app)

```
cd apps/admin   # or apps/pos
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Next step

Continue implementation per the recommended order in
`docs/specifications/engineering-notes.md` (§10): foundation/config →
domain model and schema → repositories/migrations → catalog/supplier
modules → POS session/sale lifecycle → synchronization → reporting/audit
→ hardening/packaging. Use `.claude/tasks/` to drive each step through
the relevant specialist agents.
