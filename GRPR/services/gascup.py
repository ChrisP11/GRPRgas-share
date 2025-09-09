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

from typing import Dict, Optional, Tuple, Iterable

from django.db import transaction
from django.db.models import Q, Max
from django.utils import timezone

from decimal import Decimal

from GRPR.views import _team_labels_for_game

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

    pid_list = [pair.PID1_id]
    if pair.PID2_id:                        # singleton team support
        pid_list.append(pair.PID2_id)

    nets = (
        Scorecard.objects
        .filter(GameID_id=skins_game_id,
                smID__PID_id__in=pid_list,
                HoleID_id=hole.id,)
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

# ------------------------------------------------------------------ #
# utilities used by status_for_pids                                  #
# ------------------------------------------------------------------ #

def _segment_txt(pga_wins: int, liv_wins: int,
                 pga_lbl: str = "PGA", liv_lbl: str = "LIV") -> str:
    """
    Render a match-play segment result in 'PGA +1' / 'LIV +2' / 'AS' form.
    """
    if pga_wins == liv_wins:
        return "All Square"
    if pga_wins > liv_wins:
        return f"{pga_lbl} +{pga_wins - liv_wins}"
    return f"{liv_lbl} +{liv_wins - pga_wins}"


def _slot_for_pids(skins_game_id: int, pid_list: Iterable[int]) -> Optional[str]:
    """
    Given one or more player IDs in the Skins game, return that group's
    timeslot string (e.g. '08:40'). We look up the *first* PID that has
    an invite row.
    """
    from GRPR.models import GameInvites
    gi = (
        GameInvites.objects
        .filter(GameID_id=skins_game_id, PID_id__in=list(pid_list))
        .select_related("TTID__CourseID")
        .first()
    )
    return gi.TTID.CourseID.courseTimeSlot if gi else None


def _match_pairs_for_slot(gas_game_id: int,
                          skins_game_id: int,
                          slot: str) -> Optional[Dict[str, 'GasCupPair']]:
    """
    Return {'PGA': GasCupPair, 'LIV': GasCupPair} for the foursome
    in the given timeslot. Returns None if not found.
    """
    from GRPR.models import GasCupPair, GameInvites

    pairs = (
        GasCupPair.objects
        .filter(Game_id=gas_game_id)
        .select_related("PID1", "PID2")
    )
    if not pairs:
        return None

    # preload invites of all players in the linked Skins game to map slot
    pid_list = []
    for p in pairs:
        if p.PID1_id:
            pid_list.append(p.PID1_id)
        if p.PID2_id:
            pid_list.append(p.PID2_id)

    invs = (
        GameInvites.objects
        .filter(GameID_id=skins_game_id, PID_id__in=pid_list)
        .select_related("TTID__CourseID")
    )
    slot_by_pid = {gi.PID_id: gi.TTID.CourseID.courseTimeSlot for gi in invs}

    out: Dict[str, Dict[str, 'GasCupPair']] = {}
    for p in pairs:
        s = slot_by_pid.get(p.PID1_id) or slot_by_pid.get(p.PID2_id)
        if not s:
            continue
        out.setdefault(s, {})[p.Team] = p

    return out.get(slot)


def status_for_pids(skins_game_id: int,
                    pid_list: Iterable[int],
                    thru_hole_number: int):
    """
    Return team-match status dict for the foursome containing the given
    Skins-game players, scored through `thru_hole_number`.
    """
    gas_game = _get_gascup_game_for_skins(skins_game_id)
    if not gas_game:
        return None

    labels = _team_labels_for_game(gas_game)  # e.g. ("PGA","LIV") or ("Cubs","Sox")
    t0, t1 = labels

    pid_list = [int(p) for p in pid_list]
    if not pid_list:
        return None

    slot = _slot_for_pids(skins_game_id, pid_list)
    if not slot:
        return None

    match_pairs = _match_pairs_for_slot(gas_game.id, skins_game_id, slot)
    if not match_pairs:
        return None

    pair0 = match_pairs.get(t0)
    pair1 = match_pairs.get(t1)
    if not pair0 or not pair1:
        return None

    thru = max(1, min(int(thru_hole_number), 18))

    gc_rows = (
        GasCupScore.objects
        .filter(Game_id=gas_game.id,
                Hole__HoleNumber__lte=thru,
                Pair_id__in=[pair0.id, pair1.id])
        .select_related("Hole")
    )

    hole_map = {}  # hole_no -> {t0:net, t1:net}
    for r in gc_rows:
        hn = r.Hole.HoleNumber
        d = hole_map.setdefault(hn, {})
        if r.Pair_id == pair0.id:
            d[t0] = r.NetScore
        else:
            d[t1] = r.NetScore

    f_0 = f_1 = b_0 = b_1 = 0
    for hn, d in hole_map.items():
        n0 = d.get(t0)
        n1 = d.get(t1)
        if n0 is None or n1 is None:
            continue
        if n0 < n1:
            (f_0 if hn <= 9 else b_0).__iadd__(1)
        elif n1 < n0:
            (f_1 if hn <= 9 else b_1).__iadd__(1)

    # Use labels in segment text
    front_txt   = _segment_txt(f_0, f_1, t0, t1)
    back_txt    = _segment_txt(b_0, b_1, t0, t1)
    overall_txt = _segment_txt(f_0 + b_0, f_1 + b_1, t0, t1)

    diff   = (f_0 + b_0) - (f_1 + b_1)
    leader = t0 if diff > 0 else (t1 if diff < 0 else None)

    return {
        "front":   front_txt,
        "back":    back_txt,
        "overall": overall_txt,
        "thru":    thru,
        "leader":  leader,
        "diff":    abs(diff),
        # keep the detailed counts (names imply the first/second label role)
        "f_pga":   f_0,
        "f_liv":   f_1,
        "b_pga":   b_0,
        "b_liv":   b_1,
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


def format_status_human_verbose(status: dict, pga_label: str, liv_label: str) -> str:
    """
    Verbose banner string with pair labels:

    'Hunter/Griffin (PGA) up 1 on Front, AS on Back, up 2 Overall (thru 7).'

    `status` comes from status_for_pids() and includes hole-win counts:
      f_pga, f_liv, b_pga, b_liv, thru
    """
    # fall back to generic team names when label missing
    pga_name = f"{pga_label} (PGA)" if pga_label else "Team PGA"
    liv_name = f"{liv_label} (LIV)" if liv_label else "Team LIV"

    f_pga = status["f_pga"]; f_liv = status["f_liv"]
    b_pga = status["b_pga"]; b_liv = status["b_liv"]
    thru  = status.get("thru", 0)

    def seg_phrase(delta: int, seg: str) -> str:
        if delta == 0:
            return f"All Square on {seg}"
        if delta > 0:
            return f"{pga_name} up {delta} on {seg}"
        return f"{liv_name} up {abs(delta)} on {seg}"

    front_delta   = f_pga - f_liv
    back_delta    = b_pga - b_liv
    overall_delta = (f_pga + b_pga) - (f_liv + b_liv)

    parts = []
    parts.append(seg_phrase(front_delta, "Front"))
    if thru >= 10:  # only show Back once they've played a Back hole
        parts.append(seg_phrase(back_delta, "Back"))
    parts.append(seg_phrase(overall_delta, "Overall"))

    return ", ".join(parts) + f" (thru {thru})."


# deprecated, can be deleted
# def _segment_txt(for_cnt: int, ag_cnt: int, for_lbl: str, ag_lbl: str) -> str:
#     """
#     Format segment result: lbl +/-N or AS.
#     """
#     if for_cnt > ag_cnt:
#         return f"{for_lbl} +{for_cnt - ag_cnt}"
#     if ag_cnt > for_cnt:
#         return f"{ag_lbl} +{ag_cnt - for_cnt}"
#     return "AS"


# ====================================================================== #
#  Summary helpers (for leaderboard)                                     #
# ====================================================================== #

from decimal import Decimal
from typing import Tuple

FRONT_HOLES = set(range(1, 10))
BACK_HOLES  = set(range(10, 19))


def _fmt_lead(delta: int, labels: tuple[str, str]) -> str:
    """Return '<t0> +1', '<t1> +2', or 'All Square'."""
    if delta == 0:
        return "All Square"
    side = labels[0] if delta > 0 else labels[1]
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


def _format_total_pts(t0: Decimal, t1: Decimal, labels: tuple[str, str]) -> str:
    """
    Return '<t0> X – Y <t1>' with .5 as .5 and no trailing .0.
    """
    def _fmt(d: Decimal) -> str:
        if d == d.to_integral():
            return str(int(d))
        return f"{d.normalize()}"
    return f"{labels[0]} {_fmt(t0)} – {_fmt(t1)} {labels[1]}"


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
    Return (rows, totals) for display:
      rows   -> list of dicts per foursome
      totals -> {"pga": "...", "liv": "..."} cumulative points
                (keys kept for backwards compatibility; values map to team0/team1)
    """
    from GRPR.models import GasCupPair, GameInvites, GasCupOverride

    pairs = (
        GasCupPair.objects
        .filter(Game_id=gas_game_id)
        .select_related("PID1", "PID2", "Game")
    )
    if not pairs:
        return [], {"pga": "0", "liv": "0"}

    gas_game = pairs[0].Game
    labels   = _team_labels_for_game(gas_game)  # ("PGA","LIV") or ("Cubs","Sox") etc.
    t0, t1   = labels

    skins_game_id = gas_game.AssocGame

    pid_list = []
    for p in pairs:
        if p.PID1_id: pid_list.append(p.PID1_id)
        if p.PID2_id: pid_list.append(p.PID2_id)

    invites = (
        GameInvites.objects
        .filter(GameID_id=skins_game_id, PID_id__in=pid_list)
        .select_related("TTID__CourseID")
    )
    slot_by_pid = {gi.PID_id: gi.TTID.CourseID.courseTimeSlot for gi in invites}

    # slot -> { label: GasCupPair }
    matches = {}
    for p in pairs:
        slot = slot_by_pid.get(p.PID1_id) or slot_by_pid.get(p.PID2_id)
        if not slot:
            continue
        matches.setdefault(slot, {})[p.Team] = p

    overrides_qs = GasCupOverride.objects.filter(Game_id=gas_game_id)
    overrides    = {ov.Slot: ov for ov in overrides_qs}

    t0_total = Decimal("0")
    t1_total = Decimal("0")

    rows_out = []

    for slot in sorted(matches.keys()):
        # Manual override takes precedence
        if slot in overrides:
            ov = overrides[slot]
            rows_out.append({
                "label":   slot,
                "front":   ov.Front_txt or "—",
                "back":    ov.Back_txt  or "—",
                "overall": ov.Overall_txt or "—",
                "thru":    18,
                "total":   _format_total_pts(ov.PGA_pts, ov.LIV_pts, labels),
                "note":    ov.Note,
            })
            t0_total += ov.PGA_pts
            t1_total += ov.LIV_pts
            continue

        match_pairs = matches[slot]
        pair0 = match_pairs.get(t0)
        pair1 = match_pairs.get(t1)
        if not pair0 or not pair1:
            continue

        scores_by_hole = _scores_for_match(gas_game_id, pair0.id, pair1.id)
        thru = max(scores_by_hole.keys()) if scores_by_hole else 0

        front_delta   = _segment_delta(scores_by_hole, FRONT_HOLES)
        back_delta    = _segment_delta(scores_by_hole,  BACK_HOLES)
        overall_delta = _segment_delta(scores_by_hole, FRONT_HOLES | BACK_HOLES)

        front_str   = _fmt_lead(front_delta, labels)   if thru >= 1  else None
        back_str    = _fmt_lead(back_delta, labels)    if thru >= 10 else None
        overall_str = _fmt_lead(overall_delta, labels) if thru >= 1  else None

        # award points for completed segments
        s0 = s1 = Decimal("0")
        if thru >= 9:
            f0, f1 = _pts_from_segment(front_delta)
            s0 += f0; s1 += f1
        if thru >= 18:
            b0, b1 = _pts_from_segment(back_delta)
            o0, o1 = _pts_from_segment(overall_delta)
            s0 += (b0 + o0); s1 += (b1 + o1)

        t0_total += s0
        t1_total += s1

        rows_out.append({
            "label":   slot,
            "front":   front_str,
            "back":    back_str,
            "overall": overall_str,
            "thru":    thru,
            "total":   _format_total_pts(s0, s1, labels),
        })

    def _fmt_pts(d: Decimal) -> str:
        if d == d.to_integral():
            return str(int(d))
        return f"{d.normalize()}"

    # NOTE: keep keys "pga"/"liv" for compatibility; they correspond to labels[0]/labels[1]
    totals = {"pga": _fmt_pts(t0_total), "liv": _fmt_pts(t1_total)}
    return rows_out, totals


# ------------------------------------------------------------------ #
#  Team labels / roster utilities                                    #
# ------------------------------------------------------------------ #

def _pair_label(pair: GasCupPair) -> str:
    """
    Human label for a pair: 'Hunter/Griffin' or 'Hunter (solo)'.
    Uses LastName only for brevity (matches your app style).
    """
    ln1 = pair.PID1.LastName
    if pair.PID2_id:
        ln2 = pair.PID2.LastName
        return f"{ln1}/{ln2}"
    return f"{ln1} (solo)"


def rosters_for_game(gas_game_id: int):
    from GRPR.models import GasCupPair, GameInvites

    pairs = (
        GasCupPair.objects
        .filter(Game_id=gas_game_id)
        .select_related("PID1", "PID2", "Game")
    )
    if not pairs:
        return []

    gas_game = pairs[0].Game
    labels   = _team_labels_for_game(gas_game)  # ("PGA","LIV") or ("Cubs","Sox")
    t0, t1   = labels

    skins_game_id = gas_game.AssocGame

    pid_list = []
    for p in pairs:
        if p.PID1_id: pid_list.append(p.PID1_id)
        if p.PID2_id: pid_list.append(p.PID2_id)

    invites = (
        GameInvites.objects
        .filter(GameID_id=skins_game_id, PID_id__in=pid_list)
        .select_related("TTID__CourseID")
    )
    slot_by_pid = {gi.PID_id: gi.TTID.CourseID.courseTimeSlot for gi in invites}

    # timeslot -> { label: "Hunter/Griffin" }
    slot_map = {}
    for p in pairs:
        slot = slot_by_pid.get(p.PID1_id) or slot_by_pid.get(p.PID2_id)
        if not slot:
            continue
        slot_map.setdefault(slot, {})[p.Team] = _pair_label(p)

    rows = []
    for slot in sorted(slot_map.keys()):
        d = slot_map[slot]
        rows.append({
            "label": slot,
            # keep keys "pga"/"liv" for template, but fill using current labels
            "pga":   d.get(t0, "—"),
            "liv":   d.get(t1, "—"),
        })
    return rows


# ------------------------------------------------------------------ #
#  Helper to get labels for a specific foursome (used in banners)    #
# ------------------------------------------------------------------ #

def pair_labels_for_pids(skins_game_id: int, pids: list[int]) -> tuple[Optional[str], Optional[str]]:
    """
    Given up to 4 player ids (all from the same Skins foursome), return
    (pga_label, liv_label) strings suitable for status banners.

    Returns (None, None) if no Gas Cup linked or mapping not found.
    """
    gas_game = _get_gascup_game_for_skins(skins_game_id)
    if not gas_game:
        return None, None

    from GRPR.models import GasCupPair, GameInvites

    # Which timeslot is this group? Grab the first PID that has an invite.
    inv = (
        GameInvites.objects
        .filter(GameID_id=skins_game_id, PID_id__in=pids)
        .select_related("TTID__CourseID")
        .first()
    )
    if not inv:
        return None, None
    slot = inv.TTID.CourseID.courseTimeSlot

    # Build mapping of slot -> {Team:pair}
    pid_list = []
    pairs = (
        GasCupPair.objects
        .filter(Game_id=gas_game.id)
        .select_related("PID1", "PID2")
    )
    for p in pairs:
        if p.PID1_id:
            pid_list.append(p.PID1_id)
        if p.PID2_id:
            pid_list.append(p.PID2_id)
    invites = (
        GameInvites.objects
        .filter(GameID_id=skins_game_id, PID_id__in=pid_list)
        .select_related("TTID__CourseID")
    )
    slot_by_pid = {gi.PID_id: gi.TTID.CourseID.courseTimeSlot for gi in invites}

    slot_map = {}
    for p in pairs:
        s = slot_by_pid.get(p.PID1_id) or slot_by_pid.get(p.PID2_id)
        if not s:
            continue
        slot_map.setdefault(s, {})[p.Team] = p

    match_pairs = slot_map.get(slot)
    if not match_pairs:
        return None, None

    pga_pair = match_pairs.get("PGA")
    liv_pair = match_pairs.get("LIV")
    pga_label = _pair_label(pga_pair) if pga_pair else None
    liv_label = _pair_label(liv_pair) if liv_pair else None
    return pga_label, liv_label
