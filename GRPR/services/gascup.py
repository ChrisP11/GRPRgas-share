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
from django.db.models import Q
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
