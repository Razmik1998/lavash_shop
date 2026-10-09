"""Fixed identifiers shared between models, services, and migrations.

Kept separate from any one model module because these constants are
referenced by more than one feature (pos_session bootstrap, sale
conversion, and the seeding migration itself).
"""

from __future__ import annotations

import uuid

# The permanent, non-interactive service account that owns the ONLINE
# PosSession row and every Sale converted from a confirmed online
# order. Never used for interactive login -- see the seeding migration
# for how its password hash is generated.
ONLINE_SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ONLINE_SYSTEM_USERNAME = "online-system"

# The fixed terminal_id for the permanent ONLINE selling terminal. The
# corresponding PosSession row is created idempotently at admin
# startup and is never closed (see pos_session bootstrap).
ONLINE_TERMINAL_ID = "ONLINE"

__all__ = [
	"ONLINE_SYSTEM_USERNAME",
	"ONLINE_SYSTEM_USER_ID",
	"ONLINE_TERMINAL_ID",
]
