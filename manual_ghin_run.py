#!/usr/bin/env python3
"""
Generate SQL:

    UPDATE "Players" SET "Index" = <index_value>
    WHERE "id" = <player_id>;

from lines like “(12:21.4)”
"""

import re
from textwrap import dedent

# ----------------------------------------------------------------------
# 1) Paste or read your data here
# ----------------------------------------------------------------------
pairs = dedent("""
    (12:21)
    (18:17.7)
    (28:8.7)
    (13:9.4)
    (22:14.4)
    (9:5.9)
    (2:21.4)
    (10:6.9)
    (24:16.7)
    (17:6.9)
    (23:12.2)
    (6:19.8)
    (30:5.8)
    (11:15.4)
    (15:15.7)
    (5:19.1)
    (26:12.3)
""").strip().splitlines()

# ----------------------------------------------------------------------
# 2) Parse and emit SQL
# ----------------------------------------------------------------------
pat = re.compile(r"\(\s*(\d+)\s*:\s*([\d.]+)\s*\)")
for line in pairs:
    m = pat.match(line)
    if not m:
        raise ValueError(f"Bad line: {line!r}")
    player_id, index_val = m.groups()
    # Build the statement. DOUBLE-quote identifiers for PostgreSQL.
    print(
        f'UPDATE "Players" '
        f'SET "Index" = {index_val} '
        f'WHERE "id" = {player_id};'
    )
