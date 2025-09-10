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
from django.db.models import Q, Max, Sum, Value, IntegerField
from django.db.models.functions import Coalesce
from django.utils import timezone

from decimal import Decimal

from GRPR.models import (
    Games,
    GameInvites,
    GasCupPair,
    GasCupScore,
    Scorecard,
    ScorecardMeta,
    CourseHoles,
)


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
def _combined_net_for_pair(anchor_game_id: int, pair: 'GasCupPair') -> int | None:
    """
    Sum ScorecardMeta.NetTotal for the partners in `pair` for the *anchor* game.
    Fallback to summing posted Scorecard.NetScore if NetTotal is not populated.
    """
    from GRPR.models import ScorecardMeta, Scorecard

    pids = [pair.PID1_id] + ([pair.PID2_id] if pair.PID2_id else [])
    if not pids:
        return None

    # primary: sum NetTotal from ScorecardMeta (coalesce nulls to 0)
    meta_sum = (
        ScorecardMeta.objects
        .filter(GameID_id=anchor_game_id, PID_id__in=pids)
        .aggregate(total=Sum(Coalesce('NetTotal', 0)))
    )['total']

    if meta_sum and int(meta_sum) > 0:
        return int(meta_sum)

    # fallback: sum posted NetScore rows from Scorecard (works mid-round)
    sc_sum = (
        Scorecard.objects
        .filter(GameID_id=anchor_game_id, smID__PID_id__in=pids)
        .aggregate(total=Sum('NetScore'))
    )['total']

    return int(sc_sum) if sc_sum is not None else None

def _team_labels_for_game(game: Games) -> tuple[str, str]:
    """
    Determine the two team labels used in this team game.
    Prefer actual pair labels; fall back by game.Type.
    """
    labels = (
        GasCupPair.objects
        .filter(Game=game)
        .values_list("Team", flat=True)
        .distinct()
    )
    labels = sorted([lbl for lbl in labels if lbl])[:2]
    if len(labels) == 2:
        return (labels[0], labels[1])
    if getattr(game, "Type", "") == "FallClassic":
        return ("Cubs", "Sox")
    return ("PGA", "LIV")


# REPLACE the old helper with this (keep the name for backward compatibility)
def _get_gascup_game_for_skins(skins_game_id: int) -> Optional[Games]:
    """
    Find the team game (GasCup or FallClassic) linked to the given Skins game.
    """
    return (
        Games.objects
        .filter(Type__in=["GasCup", "FallClassic"], AssocGame=skins_game_id)
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

def _segment_txt(w0: int, w1: int, lbl0: str, lbl1: str) -> str:
    if w0 == w1:
        return "All Square"
    if w0 > w1:
        return f"{lbl0} +{w0 - w1}"
    return f"{lbl1} +{w1 - w0}"


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
    # ... unchanged preface ...
    gas_game = _get_gascup_game_for_skins(skins_game_id)
    if not gas_game:
        return None

    lbl0, lbl1 = _team_labels_for_game(gas_game)

    slot = _slot_for_pids(skins_game_id, [int(p) for p in pid_list])
    if not slot:
        return None

    match_pairs = _match_pairs_for_slot(gas_game.id, skins_game_id, slot)
    if not match_pairs:
        return None

    pair0 = match_pairs.get(lbl0)
    pair1 = match_pairs.get(lbl1)
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

    hole_map = {}  # hole_no -> {lbl0:net, lbl1:net}
    for r in gc_rows:
        hn = r.Hole.HoleNumber
        d = hole_map.setdefault(hn, {})
        d[lbl0 if r.Pair_id == pair0.id else lbl1] = r.NetScore

    f0 = f1 = b0 = b1 = 0
    for hn, d in hole_map.items():
        n0 = d.get(lbl0); n1 = d.get(lbl1)
        if n0 is None or n1 is None:
            continue
        if n0 < n1:
            (f0 if hn <= 9 else b0).__iadd__(1)
        elif n1 < n0:
            (f1 if hn <= 9 else b1).__iadd__(1)

    front_txt   = _segment_txt(f0, f1, lbl0, lbl1)
    back_txt    = _segment_txt(b0, b1, lbl0, lbl1)
    overall_txt = _segment_txt(f0 + b0, f1 + b1, lbl0, lbl1)

    diff = (f0 + b0) - (f1 + b1)
    leader = lbl0 if diff > 0 else (lbl1 if diff < 0 else None)

    return {
        "front":   front_txt,
        "back":    back_txt,
        "overall": overall_txt,
        "thru":    thru,
        "leader":  leader,
        "diff":    abs(diff),
        # keep legacy keys so callers don’t break:
        "f_pga":   f0, "f_liv":   f1,
        "b_pga":   b0, "b_liv":   b1,
        # add labels so formatters can use them:
        "labels":  (lbl0, lbl1),
    }


def format_status_human(status: dict) -> str:
    """
    Friendly sentence using dynamic team labels.
    Falls back to PGA/LIV if labels aren't provided.
    """
    # dynamic labels (added by status_for_pids); fallback to PGA/LIV
    lbl0, lbl1 = status.get("labels", ("PGA", "LIV"))

    # keep legacy keys; f_pga/b_pga mean "wins for first label", f_liv/b_liv for second
    f0 = status.get("f_pga", 0); f1 = status.get("f_liv", 0)
    b0 = status.get("b_pga", 0); b1 = status.get("b_liv", 0)
    thru = status.get("thru", 0)

    def seg_phrase(seg_name: str, w0: int, w1: int) -> str:
        if w0 > w1:
            n = w0 - w1
            return f"Team {lbl0} up {n} on the {seg_name}"
        if w1 > w0:
            n = w1 - w0
            return f"Team {lbl1} up {n} on the {seg_name}"
        return f"All Square on the {seg_name}"

    front_p = seg_phrase("Front", f0, b0 if False else f1)  # keep signature same
    # ^^^ small note: above line was a typo in some older snippets; correct one is below:
    front_p = seg_phrase("Front", f0, f1)
    back_p  = seg_phrase("Back",  b0, b1)

    t0 = f0 + b0
    t1 = f1 + b1
    if t0 > t1:
        n = t0 - t1
        overall_p = f"Team {lbl0} up {n} Overall"
    elif t1 > t0:
        n = t1 - t0
        overall_p = f"Team {lbl1} up {n} Overall"
    else:
        overall_p = "All Square Overall"

    parts = [front_p, back_p, overall_p]

    # Combine if both front/back are AS
    if front_p == "All Square on the Front" and back_p == "All Square on the Back":
        parts = ["All Square on the Front and Back", overall_p]
    else:
        # compress if both Front/Back led by same side with same margin
        if (f0 > f1 and b0 > b1 and (f0 - f1) == (b0 - b1)):
            n = f0 - f1
            parts = [f"Team {lbl0} up {n} on the Front and Back", overall_p]
        elif (f1 > f0 and b1 > b0 and (f1 - f0) == (b1 - b0)):
            n = b1 - b0
            parts = [f"Team {lbl1} up {n} on the Front and Back", overall_p]

    body = "; ".join(parts)
    return f"{body}. Thru {thru}."


def format_status_human_verbose(status: dict, pga_label: str, liv_label: str) -> str:
    """
    Verbose banner with pair labels, but use dynamic team labels in parens.
    `pga_label`/`liv_label` are actually the pair labels (e.g., "Hunter/Griffin").
    """
    lbl0, lbl1 = status.get("labels", ("PGA", "LIV"))  # dynamic team names

    # fall back to generic names if pair label missing
    name0 = f"{pga_label} ({lbl0})" if pga_label else f"Team {lbl0}"
    name1 = f"{liv_label} ({lbl1})" if liv_label else f"Team {lbl1}"

    f0 = status.get("f_pga", 0); f1 = status.get("f_liv", 0)
    b0 = status.get("b_pga", 0); b1 = status.get("b_liv", 0)
    thru = status.get("thru", 0)

    def seg_phrase(delta: int, seg: str) -> str:
        if delta == 0:
            return f"All Square on {seg}"
        if delta > 0:
            return f"{name0} up {delta} on {seg}"
        return f"{name1} up {abs(delta)} on {seg}"

    front_delta   = f0 - f1
    back_delta    = b0 - b1
    overall_delta = (f0 + b0) - (f1 + b1)

    parts = [seg_phrase(front_delta, "Front")]
    if thru >= 10:
        parts.append(seg_phrase(back_delta, "Back"))
    parts.append(seg_phrase(overall_delta, "Overall"))

    return ", ".join(parts) + f" (thru {thru})."


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


def _format_total_pts(a: Decimal, b: Decimal, labels: tuple[str, str]) -> str:
    def _fmt(d: Decimal) -> str:
        if d == d.to_integral():
            return str(int(d))
        return f"{d.normalize()}"
    return f"{labels[0]} {_fmt(a)} – {_fmt(b)} {labels[1]}"


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
    Return (rows, totals) for the team match (Gas Cup or Fall Classic).
    rows: one per foursome with keys label/front/back/overall/thru/total
          and, for Fall Classic only, 'combined' (Cubs 144 – 147 Sox).
    totals: cumulative points {"pga": "...", "liv": "..."}.
    """
    from GRPR.models import GasCupPair, GameInvites, GasCupOverride

    pairs = (
        GasCupPair.objects
        .filter(Game_id=gas_game_id)
        .select_related("PID1", "PID2", "Game")
    )
    if not pairs:
        return [], {"pga": "0", "liv": "0"}

    team_game = pairs[0].Game                 # GasCup or FallClassic row
    anchor_game_id = team_game.AssocGame      # <-- anchor (Skins or Forty)
    team0, team1 = _team_labels_for_game(team_game)
    labels = (team0, team1)

    # preload timeslots from the *anchor* game invites
    pid_list = []
    for p in pairs:
        pid_list.extend([p.PID1_id, p.PID2_id] if p.PID2_id else [p.PID1_id])

    invites = (
        GameInvites.objects
        .filter(GameID_id=anchor_game_id, PID_id__in=pid_list)
        .select_related("TTID__CourseID")
    )
    slot_by_pid = {gi.PID_id: gi.TTID.CourseID.courseTimeSlot for gi in invites}

    # group pairs into matches by tee time
    matches: dict[str, dict[str, GasCupPair]] = {}
    for p in pairs:
        slot = slot_by_pid.get(p.PID1_id) or slot_by_pid.get(p.PID2_id)
        if not slot:
            continue
        matches.setdefault(slot, {})[p.Team] = p  # p.Team holds the stored label ("PGA"/"LIV" or "Cubs"/"Sox")

    overrides_qs = GasCupOverride.objects.filter(Game_id=gas_game_id)
    overrides    = {ov.Slot: ov for ov in overrides_qs}

    pga_total_pts = Decimal("0")
    liv_total_pts = Decimal("0")
    rows_out = []

    for slot in sorted(matches.keys()):
        # manual override path unchanged...
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
                # do not emit 'combined' on override (optional)
            })
            pga_total_pts += ov.PGA_pts
            liv_total_pts += ov.LIV_pts
            continue

        match_pairs = matches[slot]
        # For robustness, resolve pairs by label regardless of ordering stored in DB
        pga_pair = match_pairs.get("PGA") or match_pairs.get(team0)
        liv_pair = match_pairs.get("LIV") or match_pairs.get(team1)
        if not pga_pair or not liv_pair:
            # If DB 'Team' values are "Cubs"/"Sox" only, above still works via team0/team1 fallback
            continue

        scores_by_hole = _scores_for_match(gas_game_id, pga_pair.id, liv_pair.id)
        thru = max(scores_by_hole.keys()) if scores_by_hole else 0

        front_delta   = _segment_delta(scores_by_hole, FRONT_HOLES)
        back_delta    = _segment_delta(scores_by_hole,  BACK_HOLES)
        overall_delta = _segment_delta(scores_by_hole, FRONT_HOLES | BACK_HOLES)

        front_str   = _fmt_lead(front_delta, labels)   if thru >= 1  else None
        back_str    = _fmt_lead(back_delta, labels)    if thru >= 10 else None
        overall_str = _fmt_lead(overall_delta, labels) if thru >= 1  else None

        pga_pts = liv_pts = Decimal("0")
        if thru >= 9:
            f_pga, f_liv = _pts_from_segment(front_delta)
            pga_pts += f_pga; liv_pts += f_liv
        if thru >= 18:
            b_pga, b_liv = _pts_from_segment(back_delta)
            o_pga, o_liv = _pts_from_segment(overall_delta)
            pga_pts += (b_pga + o_pga); liv_pts += (b_liv + o_liv)

        pga_total_pts += pga_pts
        liv_total_pts += liv_pts

        row = {
            "label":   slot,
            "front":   front_str,
            "back":    back_str,
            "overall": overall_str,
            "thru":    thru,
            "total":   _format_total_pts(pga_pts, liv_pts, labels),
        }

        # Only for Fall Classic: add combined team nets using the *anchor* game id
        if getattr(team_game, "Type", "") == "FallClassic":
            pga_net = _combined_net_for_pair(anchor_game_id, pga_pair)
            liv_net = _combined_net_for_pair(anchor_game_id, liv_pair)
            if pga_net is not None and liv_net is not None:
                row["combined"] = f"{team0} {pga_net} \u2013 {liv_net} {team1}"

        rows_out.append(row)

    def _fmt_pts(d: Decimal) -> str:
        if d == d.to_integral():
            return str(int(d))
        return f"{d.normalize()}"

    totals = {"pga": _fmt_pts(pga_total_pts), "liv": _fmt_pts(liv_total_pts)}
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
    labels = _team_labels_for_game(gas_game)
    lbl0, lbl1 = labels

    skins_game_id = gas_game.AssocGame

    pid_list = []
    for p in pairs:
        pid_list.extend([p.PID1_id] + ([p.PID2_id] if p.PID2_id else []))

    invites = (
        GameInvites.objects
        .filter(GameID_id=skins_game_id, PID_id__in=pid_list)
        .select_related("TTID__CourseID")
    )
    slot_by_pid = {gi.PID_id: gi.TTID.CourseID.courseTimeSlot for gi in invites}

    by_slot = {}
    for p in pairs:
        slot = slot_by_pid.get(p.PID1_id) or slot_by_pid.get(p.PID2_id)
        if not slot:
            continue
        by_slot.setdefault(slot, {})[p.Team] = _pair_label(p)

    rows = []
    for slot in sorted(by_slot.keys()):
        d = by_slot[slot]
        rows.append({
            "label": slot,
            "pga":   d.get(lbl0, "—"),  # ‘pga’ key = first label column
            "liv":   d.get(lbl1, "—"),  # ‘liv’ key = second label column
        })
    return rows


# ------------------------------------------------------------------ #
#  Helper to get labels for a specific foursome (used in banners)    #
# ------------------------------------------------------------------ #

def pair_labels_for_pids(skins_game_id: int, pids: list[int]) -> tuple[Optional[str], Optional[str]]:
    gas_game = _get_gascup_game_for_skins(skins_game_id)
    if not gas_game:
        return None, None

    labels = _team_labels_for_game(gas_game)
    lbl0, lbl1 = labels

    inv = (
        GameInvites.objects
        .filter(GameID_id=skins_game_id, PID_id__in=pids)
        .select_related("TTID__CourseID")
        .first()
    )
    if not inv:
        return None, None
    slot = inv.TTID.CourseID.courseTimeSlot

    pairs = GasCupPair.objects.filter(Game_id=gas_game.id).select_related("PID1", "PID2")
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

    slot_map = {}
    for p in pairs:
        s = slot_by_pid.get(p.PID1_id) or slot_by_pid.get(p.PID2_id)
        if not s:
            continue
        slot_map.setdefault(s, {})[p.Team] = p

    mp = slot_map.get(slot)
    if not mp:
        return None, None

    p0 = mp.get(lbl0); p1 = mp.get(lbl1)
    return (_pair_label(p0) if p0 else None,
            _pair_label(p1) if p1 else None)

