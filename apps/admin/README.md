# Admin Application

Desktop app (PySide6) that is the system of record for `users`
(admin/employee accounts) in PostgreSQL. Provides:

- Login screen (Armenian UI), admin-role-only.
- Employees table + "Ավելացնել աշխատակից" (add employee) — the record
  that then lets that employee log in to the POS app.

## Setup

This app shares a local dev virtual environment with `apps/pos` (dev
convenience only — each app is independently installable via its own
`requirements.txt`):

```
cd ../..                      # repo root
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r apps/admin/requirements.txt
pip install -r apps/pos/requirements.txt
```

Then, from this directory (`apps/admin`):

```
cp .env.example .env           # edit DATABASE_URL/ADMIN_LAN_PORT if needed
alembic upgrade head            # create the users table
python src/seed.py              # creates the default admin user, prints
                                 # its one-time credentials
python src/main.py               # run the app (also starts the POS-facing
                                  # TCP login listener on ADMIN_LAN_PORT)
```

## Tests

```
pytest
```

Integration tests (`tests/integration/`) run against a real disposable
PostgreSQL database — set `TEST_DATABASE_URL` (defaults to
`postgresql+psycopg://shop_admin:changeme@localhost:5432/shop_admin_test`).
GUI tests use `pytest-qt`; set `QT_QPA_PLATFORM=offscreen` to run them
headlessly (e.g. in CI).

## Layout

```
src/
├── models/         ORM models and enums, grouped by feature
├── repositories/   Session-owning repositories, grouped by feature
├── repository.py   compatibility exports for legacy imports
├── schemas/        service-facing value objects, grouped by feature
├── services/       application services, grouped by feature
├── security.py     Argon2id password hashing
├── config.py       env-based configuration (DATABASE_URL)
├── db.py           engine/session factory
├── seed.py         one-off default-admin seed script
├── main.py         entrypoint; starts/stops the TCP listener with the app
├── networking/
│   ├── server.py       ThreadingTCPServer login listener (background thread)
│   └── protocol.py     newline-delimited JSON message (de)serialization
└── ui/
    ├── login_window.py
    ├── employees_window.py
    ├── add_employee_dialog.py
    └── workers.py          QThread helper (DB calls off the UI thread)
migrations/         Alembic migrations (this app owns the users schema)
tests/
├── unit/           AuthService/EmployeeService/security/networking, no DB or Qt
├── integration/    UserRepository against real PostgreSQL
└── gui/            pytest-qt smoke tests
```

The package `__init__.py` files preserve existing flat imports such as
`from models import User`, `from repository import UserRepository`, and
`from services import AuthService`. New code may import feature modules
directly when it benefits from a narrower dependency surface.

## Notes

- POS no longer reads the `users` table directly — it authenticates
  employees by talking to this app's TCP login listener (see
  `../pos/README.md` and `../../.claude/specs/2/task-plan.md`). This app
  is still the sole owner of the `users` schema/migrations.
