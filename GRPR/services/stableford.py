# stableford.py
from django.db import transaction
from django.utils import timezone
from GRPR.models import Games, Players, Scorecard, CourseHoles, StblTeam, StblScore

# ---- helpers -------------------------------------------------

def _anchor_id_for(game):
    return game.AssocGame or game.id

def _stableford_game_for_anchor(anchor_id):
    return (
        Games.objects
        .filter(Type="Stableford", AssocGame=anchor_id)
        .order_by("id")
        .first()
    )

def is_stableford_live(anchor_id: int) -> bool:
    return _stableford_game_for_anchor(anchor_id) is not None

def _points_for(par: int, net: int) -> int:
    # diff = Par - NetScore  (positive means under par)
    d = par - net
    if d <= -2: return 0         # double bogey or worse
    if d == -1: return 1         # bogey
    if d ==  0: return 2         # par
    if d ==  1: return 3         # birdie
    if d ==  2: return 4         # eagle
    return 5                     # albatross or better

def _initial(s: str) -> str:
    return (s or "")[:1].upper()

def _teamname_individual(p: Players) -> str:
    return f"{_initial(p.FirstName)}. {p.LastName}"

def _teamname_join_lastnames(players: list[Players]) -> str:
    # join clean last names in the order provided
    parts = []
    for p in players:
        ln = (p.LastName or "").strip()
        parts.append(ln)
    return "-".join(parts)

def _players_map(pid_list: list[int]) -> dict[int, Players]:
    qs = Players.objects.filter(id__in=pid_list).only("id", "FirstName", "LastName")
    return {p.id: p for p in qs}

# Optional: seed teams once per Stableford game based on Format and your SSOT.
transaction.atomic
def ensure_teams_for_stableford(draft, stbl_game: Games):
    """
    Build StblTeam rows for the Stableford game with TeamID & TeamName.

    Format mapping (from Games.Format):
      - "Individual" → one team per player, TeamName "F. LastName"
      - "2some"      → two-person teams from draft.state["stableford_pairs"]
                       TeamName "LastName1-LastName2"
      - "4some"      → one team per tee-time label, TeamName of all last names
                       in that foursome joined by "-"

    Idempotent via full replace:
      - Deletes existing StblTeam rows for this Stableford game
      - Recreates from current draft.state & game.Format
    """
    if not stbl_game:
        return

    fmt = (stbl_game.Format or "").strip()
    if fmt not in {"Individual", "2some", "4some"}:
        return

    state        = draft.state or {}
    assignments  = state.get("assignments") or {}           # {"8:40":[pid,...], ...}
    pairs_state  = state.get("stableford_pairs") or {}       # {"8:40":{"team1":[...],"team2":[...]}, ...}

    # Collect all PIDs we might reference
    all_pids = [pid for lst in assignments.values() for pid in lst]
    pid_to_player = _players_map(all_pids)

    # Build new rows in a deterministic order
    new_rows = []  # list of (PID, TeamID, TeamName)
    next_team_id = 1

    if fmt == "Individual":
        # deterministic: by tee slot label, then by LastName
        for label in sorted(assignments.keys()):
            slot_pids = assignments[label]
            # sort by last name for stable, human-friendly team numbering
            slot_pids = sorted(slot_pids, key=lambda pid: (pid_to_player[pid].LastName, pid))
            for pid in slot_pids:
                p = pid_to_player[pid]
                team_name = _teamname_individual(p)
                new_rows.append((pid, next_team_id, team_name))
                next_team_id += 1

    elif fmt == "2some":
        # exactly two teams per tee slot (but safe if 3-ball etc.)
        for label in sorted(assignments.keys()):
            slot = pairs_state.get(label) or {}
            for key in ("team1", "team2"):
                pids = list(slot.get(key) or [])
                if not pids:
                    continue
                players = [pid_to_player[pid] for pid in pids if pid in pid_to_player]
                team_name = _teamname_join_lastnames(players)
                for pid in pids:
                    new_rows.append((pid, next_team_id, team_name))
                next_team_id += 1

    elif fmt == "4some":
        # one team per tee-time label
        for label in sorted(assignments.keys()):
            pids = list(assignments[label] or [])
            players = [pid_to_player[pid] for pid in pids if pid in pid_to_player]
            team_name = _teamname_join_lastnames(players)
            for pid in pids:
                new_rows.append((pid, next_team_id, team_name))
            next_team_id += 1

    # Replace existing rows atomically
    StblTeam.objects.filter(Game=stbl_game).delete()
    if new_rows:
        StblTeam.objects.bulk_create([
            StblTeam(Game=stbl_game, PID_id=pid, TeamID=tid, TeamName=tname)
            for (pid, tid, tname) in new_rows
        ])

# ---- scoring entrypoint -------------------------------------

def update_for_score(scorecard_id: int):
    """
    Given a Scorecard row id that was inserted/updated, compute & upsert
    the Stableford points for the associated Stableford game (if present).
    """
    sc = (
        Scorecard.objects
        .select_related("GameID", "HoleID", "smID__PID")
        .filter(id=scorecard_id)
        .first()
    )
    if not sc:
        return

    anchor_id = _anchor_id_for(sc.GameID)
    stbl_game = _stableford_game_for_anchor(anchor_id)
    if not stbl_game:
        return  # no Stableford game in this event, nothing to do

    # Compute points from Par/NetScore
    par = sc.HoleID.Par
    net = sc.NetScore
    pts = _points_for(par, net)
    pid = sc.smID.PID_id

    # Upsert one row per (stableford game, pid, hole)
    with transaction.atomic():
        obj, created = StblScore.objects.get_or_create(
            Game=stbl_game,
            PID_id=pid,
            Hole=sc.HoleID,
            defaults={"Points": pts, "RawScore": sc.RawScore, "NetScore": net},
        )
        if not created:
            obj.Points   = pts
            obj.RawScore = sc.RawScore
            obj.NetScore = net
            obj.save(update_fields=["Points", "RawScore", "NetScore", "AlterDate"])
