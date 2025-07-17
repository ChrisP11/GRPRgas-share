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

from typing import Dict, Optional

from django.db import transaction
from django.db.models import Q, Max
from django.utils import timezone

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


