# POS Application

Desktop app (PySide6) for POS terminals. Provides:

- Login screen (Armenian UI), employee-role-only.
- Placeholder home screen after login (full sales/checkout flow is out
  of scope for this first slice).

Authenticates employees against a running `apps/admin` instance over a
TCP socket (see `.env.example`) — POS never opens a database
connection of its own.

## Setup

This app shares a local dev virtual environment with `apps/admin` (dev
convenience only — each app is independently installable via its own
`requirements.txt`):

```
cd ../..                      # repo root
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r apps/admin/requirements.txt
pip install -r apps/pos/requirements.txt
```

Then, from this directory (`apps/pos`):

```
cp .env.example .env           # edit ADMIN_HOST/ADMIN_PORT if needed
python src/main.py              # run the app (Admin must already be running)
```

On Windows, the POS uses the installed `XP-80C` printer through Windows
RAW printing. Configure `PRINTER_NAME`, `PRINTER_ENABLED`,
`RECEIPT_PAPER_WIDTH=80`, `RECEIPT_CHARS_PER_LINE=48`, `RECEIPT_CUT`,
`RECEIPT_LANGUAGE`, and `ONLINE_ORDER_URL` in `.env` or the machine
configuration. `RECEIPT_LANGUAGE` accepts `en` (the default) or `hy`; Armenian
text is rendered as raster graphics so it does not depend on the printer's
character code page. `STORE_PHONE_NUMBERS` accepts comma-separated numbers;
they are printed beside the online order details and on closeout summaries.
Receipts show the quantity unit for each item (for example, kg or pcs). After
each sale, the POS prints a receipt in the selected language. When a work
session closes, it also prints a closeout summary with cash and credit sales,
repayments, cash handover, and drawer balance. Set the online ordering URL to
the live site before enabling receipt printing.

An employee account must already exist (created from the Admin app's
"Ավելացնել աշխատակից" screen) before it can log in here. If Admin isn't
running/reachable, POS shows an error and refuses to start.

## Tests

```
pytest
```

`tests/unit/test_local_connection.py` runs a disposable TCP test server
in-process, no real Admin instance needed. GUI tests use `pytest-qt`;
set `QT_QPA_PLATFORM=offscreen` to run them headlessly.

## Layout

```
src/
├── models.py       plain domain value objects (User, Role)
├── services.py     AuthService (application layer, depends on AdminConnection)
├── config.py       env-based configuration (ADMIN_HOST, ADMIN_PORT)
├── main.py         entrypoint; blocks at startup if Admin is unreachable
├── networking/
│   ├── connection.py       AdminConnection (ABC): is_available/login
│   ├── local_connection.py LocalConnection — TCP to 127.0.0.1:ADMIN_PORT
│   └── protocol.py         newline-delimited JSON message (de)serialization
└── ui/
    ├── login_window.py
    ├── home_window.py       placeholder landing screen
    └── workers.py           QThread helper (network calls off the UI thread)
tests/
├── unit/           AuthService/LocalConnection, no real Admin process
└── gui/            pytest-qt smoke tests
```

## Notes

- POS talks to Admin over a raw TCP socket (newline-delimited JSON),
  never to PostgreSQL directly — see `../../.claude/specs/2/task-plan.md`.
- `LocalConnection` only ever targets loopback; a future `LanConnection`
  for a real cross-machine Admin is out of scope here and will require
  TLS before it can reuse this trust model.
