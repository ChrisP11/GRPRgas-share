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
(59:25.3)
(14:19.9)
(12:20.8)
(18:17.7)
(28:8.4)
(13:8.7)
(22:14.3)
(9:6.5)
(2:21.8)
(10:6.9)
(24:16.1)
(17:6.9)
(23:11.7)
(6:20.6)
(30:7.2)
(11:15.4)
(15:15.2)
(5:19.3)
(26:12.6)
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
