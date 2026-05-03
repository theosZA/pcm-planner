"""
Squad composition config for the PCM Season Planner optimiser.

Defines how many of each rider role make up a squad for a given
(SquadProfile, squad_size) combination.

SQUAD_COMPOSITIONS maps (profile, size) → {role: count}.  The counts must
sum to the squad size.  Entries are only needed for (profile, size) pairs
that actually appear in the race calendar — the optimiser will warn at
runtime if it encounters an unmapped combination.
"""

from __future__ import annotations

from optimise.model import RiderRole, SquadProfile

# Keys:   (SquadProfile, rider_capacity)
# Values: {RiderRole: count}  — must sum to rider_capacity
SQUAD_COMPOSITIONS: dict[tuple[SquadProfile, int], dict[RiderRole, int]] = {
    (SquadProfile.SPRINT, 6): {
        RiderRole.SPRINT_LEAD:    1,
        RiderRole.SPRINT_LEADOUT: 2,
        RiderRole.DOMESTIQUE:     2,
        RiderRole.FREE:           1,
    },
    (SquadProfile.SPRINT, 7): {
        RiderRole.SPRINT_LEAD:    1,
        RiderRole.SPRINT_LEADOUT: 2,
        RiderRole.DOMESTIQUE:     3,
        RiderRole.FREE:           1,
    },
    (SquadProfile.CLIMBING, 6): {
        RiderRole.CLIMBING_LEAD:       1,
        RiderRole.CLIMBING_DOMESTIQUE: 2,
        RiderRole.DOMESTIQUE:          2,
        RiderRole.FREE:                1,
    },
    (SquadProfile.CLIMBING, 7): {
        RiderRole.CLIMBING_LEAD:       1,
        RiderRole.CLIMBING_DOMESTIQUE: 2,
        RiderRole.DOMESTIQUE:          3,
        RiderRole.FREE:                1,
    },
    (SquadProfile.STAGE_RACE, 6): {
        RiderRole.CLIMBING_LEAD:       1,
        RiderRole.CLIMBING_DOMESTIQUE: 2,
        RiderRole.SPRINT_LEAD:         1,
        RiderRole.SPRINT_LEADOUT:      1,
        RiderRole.DOMESTIQUE:          1,
    },
    (SquadProfile.STAGE_RACE, 7): {
        RiderRole.CLIMBING_LEAD:       1,
        RiderRole.CLIMBING_DOMESTIQUE: 2,
        RiderRole.SPRINT_LEAD:         1,
        RiderRole.SPRINT_LEADOUT:      1,
        RiderRole.DOMESTIQUE:          1,
        RiderRole.FREE:                1,
    },
    (SquadProfile.STAGE_RACE, 8): {
        RiderRole.CLIMBING_LEAD:       1,
        RiderRole.CLIMBING_DOMESTIQUE: 3,
        RiderRole.SPRINT_LEAD:         1,
        RiderRole.SPRINT_LEADOUT:      1,
        RiderRole.DOMESTIQUE:          1,
        RiderRole.FREE:                1,
    },
    (SquadProfile.TIME_TRIAL, 3): {
        RiderRole.TIME_TRIAL: 3,
    },
}
