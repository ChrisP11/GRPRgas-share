# GRPR/services/gascup.py
"""
Gas Cup scoring utilities.

We derive Gas Cup team best-ball *net* scores from the per-player NetScore
rows already written to Scorecard for the *Skins* game.

Usage
-----
Call `gascup.update_for_score(score_id)` immediately after saving or updating
a Scorecard row. Safe to call unconditionally: if no Gas Cup is linked to the
Skins game (Games.AssocGame), the function returns immediately.

Idempotent
----------
Whenever called, we recompute the *entire match* (both teams) result for the
specific hole that changed, and update/overwrite the corresponding
GasCupScore rows (Pair, Hole).
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from django.db import transaction
from django.db.models import Q, Max
from django.utils import timezone

from decimal import Decimal

from GRPR.models import (
    Games,
    GameInvites,
    GasCupPair,
    GasCupScore,
    Scorecard,
    CourseHoles,
)

# ------------------------------------------------------------------ #
# Public API                                                         #
# ------------------------------------------------------------------ #
def update_for_score(score_id: int) -> None:
    """
    Update Gas Cup derived scoring for the hole touched by Scorecard pk=score_id.

    Steps:
      1. Load Scorecard row (Skins game).
      2. Find Gas Cup game linked via Games.AssocGame.
      3. Determine the foursome (timeslot) for the player whose score changed.
      4. For BOTH teams in that foursome, compute their best-ball net for this hole.
      5. Upsert (Pair, Hole) rows in GasCupScore.

    Silently returns if any prerequisite is missing (no Gas Cup, missing invites, etc.).
    """
    try:
        # Follow smID->PID and HoleID in one DB hit
        sc = (
            Scorecard.objects
            .select_related("GameID", "HoleID", "smID__PID")
            .get(pk=score_id)
        )
    except Scorecard.DoesNotExist:
        return

    skins_game = sc.GameID  # Games instance (Type='Skins')
    gas_game = _get_gascup_game_for_skins(skins_game.id)
    if not gas_game:
        return  # no Gas Cup tied to this Skins game

    hole = sc.HoleID  # CourseHoles instance
    player_pid = sc.smID.PID_id

    # Build match map once
    match_map = _pairs_by_timeslot(gas_game, skins_game.id)
    if not match_map:
        return

    # Which timeslot is THIS player in?
    slot = _timeslot_for_pid_in_skins(player_pid, skins_game.id)
    if not slot:
        return

    match_pairs = match_map.get(slot)
    if not match_pairs:
        return

    # Recompute best-ball for BOTH teams for this hole
    for pair in match_pairs.values():  # dict{'PGA':pair,'LIV':pair}
        net = _best_net_for_pair_on_hole(pair, hole, skins_game.id)
        if net is not None:
            _upsert_gascupscore(gas_game.id, pair.id, hole.id, net)
        else:
            # no posted score yet → remove existing row so downstream “thru” calc is correct
            GasCupScore.objects.filter(
                Game_id=gas_game.id,
                Pair_id=pair.id,
                Hole_id=hole.id,
            ).delete()


# ------------------------------------------------------------------ #
# Internal helpers                                                   #
# ------------------------------------------------------------------ #
def _get_gascup_game_for_skins(skins_game_id: int) -> Optional[Games]:
    """
    Find the Gas Cup game whose AssocGame == skins_game_id.
    Return latest if multiple (should not happen).
    """
    return (
        Games.objects
        .filter(Type="GasCup", AssocGame=skins_game_id)
        .order_by("-id")
        .first()
    )


def _timeslot_for_pid_in_skins(pid: int, skins_game_id: int) -> Optional[str]:
    """
    Return the tee-time slot string for the given player in the Skins game.
    """
    gi = (
        GameInvites.objects
        .select_related("TTID__CourseID")
        .filter(GameID_id=skins_game_id, PID_id=pid)
        .first()
    )
    return gi.TTID.CourseID.courseTimeSlot if gi else None


def _pairs_by_timeslot(gas_game: Games, skins_game_id: int) -> Dict[str, Dict[str, GasCupPair]]:
    """
    Build a mapping:
        { timeslot: { 'PGA': GasCupPair, 'LIV': GasCupPair } }

    We infer each pair's timeslot from *either* partner's GameInvite
    in the Skins game (both must be same foursome by rule).
    """
    pairs = GasCupPair.objects.filter(Game=gas_game).select_related("PID1", "PID2")
    if not pairs:
        return {}

    # Preload invites for all PIDs
    pid_list = []
    for p in pairs:
        pid_list.extend([p.PID1_id, p.PID2_id])

    invites = (
        GameInvites.objects
        .filter(GameID_id=skins_game_id, PID_id__in=pid_list)
        .select_related("TTID__CourseID")
    )
    slot_by_pid = {gi.PID_id: gi.TTID.CourseID.courseTimeSlot for gi in invites}

    out: Dict[str, Dict[str, GasCupPair]] = {}
    for p in pairs:
        slot = slot_by_pid.get(p.PID1_id) or slot_by_pid.get(p.PID2_id)
        if not slot:
            continue
        out.setdefault(slot, {})[p.Team] = p
    return out


def _best_net_for_pair_on_hole(pair: GasCupPair, hole: CourseHoles, skins_game_id: int) -> Optional[int]:
    """
    Return the LOWER of the two partners' NetScore on this hole,
    or None if neither has posted.
    """
    nets = (
        Scorecard.objects
        .filter(
            GameID_id=skins_game_id,
            smID__PID_id__in=[pair.PID1_id, pair.PID2_id],
            HoleID_id=hole.id,
        )
        .values_list("NetScore", flat=True)
    )
    nets = [n for n in nets if n is not None]
    return min(nets) if nets else None


def _upsert_gascupscore(game_id: int, pair_id: int, hole_id: int, net: int) -> None:
    """
    Insert or update the GasCupScore for this (game, pair, hole).
    """
    GasCupScore.objects.update_or_create(
        Game_id=game_id,
        Pair_id=pair_id,
        Hole_id=hole_id,
        defaults={"NetScore": net},
    )



# ------------------------------------------------------------------ #
# Match status helpers (Front / Back / Overall)                      #
# ------------------------------------------------------------------ #
def status_for_pids(skins_game_id: int, pid_list, thru_hole_number: int):
    """
    Return a dict describing Gas Cup status for the foursome that contains the
    given player ids *in the Skins game* up through the given hole number.

    pid_list can be any iterable of the 4 player ids in the group; we’ll match
    the two GasCupPair rows (PGA & LIV) that intersect those PIDs.

    Dict returned:
        {
          "front":   "PGA +1" | "LIV +2" | "AS",
          "back":    "AS" | ...,
          "overall": "PGA +3" | ...,
          "thru":    5,        # hole number passed in (clamped 1-18)
          "leader":  "PGA" | "LIV" | None,   # side leading overall
          "diff":    1 | 0 | ...
        }
    or None if no Gas Cup linked or pairs not found.
    """
    # find the GasCup game
    gas_game = _get_gascup_game_for_skins(skins_game_id)
    if not gas_game:
        return None

    pid_set = set(int(p) for p in pid_list)

    # find the two pairs that belong to this foursome
    pairs = (
        GasCupPair.objects
        .filter(Game=gas_game)
        .select_related("PID1", "PID2")
    )

    pga_pair = None
    liv_pair = None
    for p in pairs:
        # each pair should have both partners inside pid_set
        if p.PID1_id in pid_set and p.PID2_id in pid_set:
            if p.Team == "PGA":
                pga_pair = p
            elif p.Team == "LIV":
                liv_pair = p

    if not (pga_pair and liv_pair):
        return None

    # clamp hole
    thru = max(1, min(int(thru_hole_number), 18))

    # collect GasCupScore rows thru that hole
    gc_rows = (
        GasCupScore.objects
        .filter(Game=gas_game, Hole__HoleNumber__lte=thru,
                Pair_id__in=[pga_pair.id, liv_pair.id])
        .select_related("Hole")
    )

    # pivot: hole -> { 'PGA':net, 'LIV':net }
    hole_map = {}
    for r in gc_rows:
        hole_no = r.Hole.HoleNumber
        d = hole_map.setdefault(hole_no, {})
        if r.Pair_id == pga_pair.id:
            d["PGA"] = r.NetScore
        else:
            d["LIV"] = r.NetScore

    # count won holes
    f_pga = f_liv = b_pga = b_liv = 0
    for hole_no, d in hole_map.items():
        if "PGA" not in d or "LIV" not in d:
            continue  # missing score on one side yet
        if d["PGA"] < d["LIV"]:
            if hole_no <= 9:
                f_pga += 1
            else:
                b_pga += 1
        elif d["LIV"] < d["PGA"]:
            if hole_no <= 9:
                f_liv += 1
            else:
                b_liv += 1
        # equal → halved (no increment)

    front_txt   = _segment_txt(f_pga, f_liv, "PGA", "LIV")
    back_txt    = _segment_txt(b_pga, b_liv, "PGA", "LIV")
    overall_txt = _segment_txt(f_pga + b_pga, f_liv + b_liv, "PGA", "LIV")

    # numeric overall diff for convenience
    diff = (f_pga + b_pga) - (f_liv + b_liv)
    leader = "PGA" if diff > 0 else "LIV" if diff < 0 else None

    return {
        "front":   front_txt,   # "PGA +1" | "LIV +2" | "AS"
        "back":    back_txt,
        "overall": overall_txt,
        "thru":    thru,
        "leader":  leader,      # "PGA"|"LIV"|None
        "diff":    abs(diff),   # numeric overall diff
        # raw counts for richer formatting
        "f_pga":   f_pga,
        "f_liv":   f_liv,
        "b_pga":   b_pga,
        "b_liv":   b_liv,
    }


def format_status_human(status: dict) -> str:
    """
    Convert the status dict from status_for_pids() into a friendly sentence.

    Examples:
      Team PGA is up 1 on the Front and 1 Overall; AS on the Back. Thru 5.
      All Square on the Front and Back; Team LIV up 2 Overall. Thru 14.
      Team PGA wins the Front 3&2 ...  (← not implementing holes-to-play math yet)

    Rules:
      • We always show Overall.
      • We show Front and Back if they differ OR user may want to see them;
        (for now we always show all three, compact grammar).
      • “AS” => “All Square”.
      • Singular/plural: “up 1” vs “up 2”.
      • We end with “Thru N.” (use status["thru"]).
    """
    f_pga = status["f_pga"]; f_liv = status["f_liv"]
    b_pga = status["b_pga"]; b_liv = status["b_liv"]
    thru  = status["thru"]

    def seg_phrase(seg_name: str, pga_wins: int, liv_wins: int) -> str:
        if pga_wins > liv_wins:
            n = pga_wins - liv_wins
            return f"Team PGA up {n} on the {seg_name}"
        if liv_wins > pga_wins:
            n = liv_wins - pga_wins
            return f"Team LIV up {n} on the {seg_name}"
        return f"All Square on the {seg_name}"

    front_p = seg_phrase("Front", f_pga, f_liv)
    back_p  = seg_phrase("Back",  b_pga, b_liv)

    # overall uses totals
    t_pga = f_pga + b_pga
    t_liv = f_liv + b_liv
    if t_pga > t_liv:
        n = t_pga - t_liv
        overall_p = f"Team PGA up {n} Overall"
    elif t_liv > t_pga:
        n = t_liv - t_pga
        overall_p = f"Team LIV up {n} Overall"
    else:
        overall_p = "All Square Overall"

    # join – prefer: Front and Back; Overall separated by semicolon
    # e.g. "Team PGA up 1 on the Front and 1 Overall; AS on the Back."
    # But reuse already-built phrases to avoid recomputing numbers.
    # We'll build: "<Front>; <Back>; <Overall>." then tighten.
    parts = [front_p, back_p, overall_p]

    # Slightly smarter join: combine AS segments
    # If front/back are both AS, say "All Square on the Front and Back".
    if "All Square on the Front" == front_p and "All Square on the Back" == back_p:
        parts = ["All Square on the Front and Back", overall_p]
    else:
        # if both front/back led by same side with same margin, compress
        if (f_pga > f_liv and b_pga > b_liv and
            (f_pga - f_liv) == (b_pga - b_liv)):
            n = f_pga - f_liv
            parts = [f"Team PGA up {n} on the Front and Back", overall_p]
        elif (f_liv > f_pga and b_liv > b_pga and
              (f_liv - f_pga) == (b_liv - b_pga)):
            n = b_liv - b_pga  # same margin
            parts = [f"Team LIV up {n} on the Front and Back", overall_p]

    body = "; ".join(parts)
    return f"{body}. Thru {thru}."



def _segment_txt(for_cnt: int, ag_cnt: int, for_lbl: str, ag_lbl: str) -> str:
    """
    Format segment result: lbl +/-N or AS.
    """
    if for_cnt > ag_cnt:
        return f"{for_lbl} +{for_cnt - ag_cnt}"
    if ag_cnt > for_cnt:
        return f"{ag_lbl} +{ag_cnt - for_cnt}"
    return "AS"


# ====================================================================== #
#  Summary helpers (for leaderboard)                                     #
# ====================================================================== #

from decimal import Decimal
from typing import Tuple

FRONT_HOLES = set(range(1, 10))
BACK_HOLES  = set(range(10, 19))


def _fmt_lead(delta: int) -> str:
    """Return 'PGA +1', 'LIV +2', or 'AS' (all square) for 0."""
    if delta == 0:
        return "AS"
    side = "PGA" if delta > 0 else "LIV"
    return f"{side} +{abs(delta)}"


def _pts_from_segment(delta: int) -> Tuple[Decimal, Decimal]:
    """
    Convert a won/lost AS delta into point allocations.
    +ve delta => PGA wins segment → (1, 0)
    -ve delta => LIV wins segment → (0, 1)
     0 delta  => tied segment    → (0.5, 0.5)
    """
    if delta > 0:
        return Decimal("1"), Decimal("0")
    if delta < 0:
        return Decimal("0"), Decimal("1")
    return Decimal("0.5"), Decimal("0.5")


def _format_total_pts(pga: Decimal, liv: Decimal) -> str:
    """
    Return a clean 'PGA X – Y LIV' string with no trailing .0
    and .5 rendered as .5.
    """
    def _fmt(d: Decimal) -> str:
        if d == d.to_integral():
            return str(int(d))
        # show 0.5 not Decimal('0.5')
        return f"{d.normalize()}"
    return f"PGA {_fmt(pga)} – {_fmt(liv)} LIV"


def _segment_delta(scores_by_hole: dict[int, Tuple[int, int]], holes: set[int]) -> int:
    """
    Given {hole_number: (pga_net, liv_net)}, compute match-play delta
    for the subset of hole_numbers in 'holes'.
    Return (#holes PGA won) - (#holes LIV won). Ties ignored.
    """
    pga_wins = liv_wins = 0
    for hn, (pga_net, liv_net) in scores_by_hole.items():
        if hn not in holes:
            continue
        if pga_net is None or liv_net is None:
            continue
        if pga_net < liv_net:
            pga_wins += 1
        elif liv_net < pga_net:
            liv_wins += 1
    return pga_wins - liv_wins


def _scores_for_match(gas_game_id: int, pga_pair_id: int, liv_pair_id: int) -> dict[int, Tuple[Optional[int], Optional[int]]]:
    """
    Build {hole_number: (pga_net, liv_net)} for the given two pairs in
    a single Gas Cup match (one foursome).

    We pull GasCupScore rows for both pairs and merge.
    """
    from GRPR.models import GasCupScore  # local import to avoid cycles

    # fetch all rows for both pairs
    rows = (
        GasCupScore.objects
        .filter(Game_id=gas_game_id, Pair_id__in=[pga_pair_id, liv_pair_id])
        .select_related("Hole")
        .values("Hole__HoleNumber", "Pair_id", "NetScore")
    )
    out: dict[int, list[Tuple[int, int]]] = {}
    for r in rows:
        hn = r["Hole__HoleNumber"]
        out.setdefault(hn, [None, None])  # [pga_net, liv_net]
        if r["Pair_id"] == pga_pair_id:
            out[hn][0] = r["NetScore"]
        else:
            out[hn][1] = r["NetScore"]

    # collapse to mapping with tuples
    return {hn: tuple(vals) for hn, vals in out.items()}


def summary_for_game(gas_game_id: int):
    """
    Return (rows, totals):

    rows   -> list of dicts (one per foursome) each with:
              label/front/back/overall/thru/total  (as before)
    totals -> {"pga": "X", "liv": "Y"} cumulative match points
              across *completed* segments of all matches.

    Segment-complete rules:
      Front  counts after thru >= 9
      Back   counts after thru >= 18
      Overall counts after thru >= 18
    """
    from GRPR.models import GasCupPair, GameInvites

    # Pull all pairs for this Gas Cup game.
    pairs = (
        GasCupPair.objects
        .filter(Game_id=gas_game_id)
        .select_related("PID1", "PID2", "Game")
    )
    if not pairs:
        return [], {"pga": "0", "liv": "0"}

    # Linked Skins game (GasCup.Game.AssocGame)
    gas_game = pairs[0].Game
    skins_game_id = gas_game.AssocGame

    # Preload timeslots for all players in these pairs.
    pid_list = []
    for p in pairs:
        pid_list.extend([p.PID1_id, p.PID2_id])
    invites = (
        GameInvites.objects
        .filter(GameID_id=skins_game_id, PID_id__in=pid_list)
        .select_related("TTID__CourseID")
    )
    slot_by_pid = {gi.PID_id: gi.TTID.CourseID.courseTimeSlot for gi in invites}

    # Group GasCupPair rows into matches keyed by timeslot.
    matches = {}
    for p in pairs:
        slot = slot_by_pid.get(p.PID1_id) or slot_by_pid.get(p.PID2_id)
        if not slot:
            continue
        matches.setdefault(slot, {})[p.Team] = p

    # Totals accumulators
    pga_total_pts = Decimal("0")
    liv_total_pts = Decimal("0")

    rows_out = []

    # stable sort by timeslot string
    for slot in sorted(matches.keys()):
        match_pairs = matches[slot]
        pga_pair = match_pairs.get("PGA")
        liv_pair = match_pairs.get("LIV")
        if not pga_pair or not liv_pair:
            continue

        # scores_by_hole: hn -> (pga_net, liv_net)
        scores_by_hole = _scores_for_match(gas_game_id, pga_pair.id, liv_pair.id)

        # compute "thru" = max hole where at least one side has a score
        thru = max(scores_by_hole.keys()) if scores_by_hole else 0

        # deltas
        front_delta   = _segment_delta(scores_by_hole, FRONT_HOLES)
        back_delta    = _segment_delta(scores_by_hole,  BACK_HOLES)
        overall_delta = _segment_delta(scores_by_hole, FRONT_HOLES | BACK_HOLES)

        # segment strings (Back waits until any Back hole posted)
        front_str   = _fmt_lead(front_delta)   if thru >= 1  else None
        back_str    = _fmt_lead(back_delta)    if thru >= 10 else None
        overall_str = _fmt_lead(overall_delta) if thru >= 1  else None

        # ----- award points for completed segments -----
        pga_pts = liv_pts = Decimal("0")
        if thru >= 9:   # Front complete
            f_pga, f_liv = _pts_from_segment(front_delta)
            pga_pts += f_pga
            liv_pts += f_liv
        if thru >= 18:  # Back & Overall complete
            b_pga, b_liv = _pts_from_segment(back_delta)
            o_pga, o_liv = _pts_from_segment(overall_delta)
            pga_pts += (b_pga + o_pga)
            liv_pts += (b_liv + o_liv)

        # accumulate across matches
        pga_total_pts += pga_pts
        liv_total_pts += liv_pts

        rows_out.append({
            "label":   slot,
            "front":   front_str,
            "back":    back_str,
            "overall": overall_str,
            "thru":    thru,
            "total":   _format_total_pts(pga_pts, liv_pts),
        })

    # final cumulative
    def _fmt_pts(d: Decimal) -> str:
        if d == d.to_integral():
            return str(int(d))
        return f"{d.normalize()}"

    totals = {"pga": _fmt_pts(pga_total_pts), "liv": _fmt_pts(liv_total_pts)}
    return rows_out, totals

