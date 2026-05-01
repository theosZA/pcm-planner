"""
Data model for the PCM Season Planner optimiser.

Defines the domain objects that represent the planning problem:

- Rider: a member of the player's squad, with all relevant performance stats.
- Race: a race the player's team is entered in, with scheduling and squad-size data.
- PlannerData: the complete snapshot loaded from the planner DB for a single
  optimisation run, with aggregate computed properties used by validation and
  the optimiser alike.

All data flows into these classes from db.py and out to constraints.py and
the optimisation logic. Nothing in this module touches the database directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Rider:
    """A rider on the player's team, with stats used for race scoring."""

    id: int                 # planner DB primary key
    source_rider_id: int    # original PCM rider ID
    display_name: str

    # Performance stats — Optional because a stat row might theoretically be absent.
    flat: Optional[int] = None
    hill: Optional[int] = None
    medium_mountain: Optional[int] = None
    mountain: Optional[int] = None
    time_trial: Optional[int] = None
    prologue: Optional[int] = None
    cobble: Optional[int] = None
    sprint: Optional[int] = None
    acceleration: Optional[int] = None
    stamina: Optional[int] = None
    resistance: Optional[int] = None
    recovery: Optional[int] = None
    baroudeur: Optional[int] = None


@dataclass
class Race:
    """A race the player's team is entered in."""

    id: int                     # planner DB primary key
    source_race_id: int         # original PCM race ID
    name: str
    abbreviation: str
    level: str                  # e.g. "grand_tour", "world_tour", "pro"
    start_date: Optional[str]   # ISO-8601 date, derived from imported stage dates
    end_date: Optional[str]     # ISO-8601 date, derived from imported stage dates
    race_days: int              # number of selected stages imported
    rider_capacity: int         # squad size required (from race class max_riders)
    is_stage_race: bool
    invitation_state_id: int    # see team_race_entry.invitation_state_id


@dataclass
class PlannerData:
    """Complete snapshot of planning data loaded from the planner database.

    This is the single input to all validation and optimisation logic — the
    optimiser should never query the database directly.
    """

    player_team_name: str
    player_name: str
    riders: list[Rider]
    races: list[Race]

    @property
    def total_race_days_demanded(self) -> int:
        """Total rider-days required: sum of (race_days × rider_capacity) across all races.

        This represents the total "work" that must be distributed across the squad.
        For example, a 21-stage Grand Tour with a squad of 8 contributes 168 rider-days.
        """
        return sum(r.race_days * r.rider_capacity for r in self.races)

    @property
    def total_rider_days_available(self) -> int:
        """Maximum rider-days the squad can cover: 75-day cap × number of riders."""
        return 75 * len(self.riders)
