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

import enum
from dataclasses import dataclass, field
from typing import Optional


class RaceClass(enum.Enum):
    """PCM race-class constants, mapping clean names to raw DB strings."""

    WORLD_CHAMPIONSHIP        = "WorldChampionship"
    WORLD_CHAMPIONSHIP_ITT    = "WorldChampionshipITT"
    EUROPEAN_CHAMPIONSHIP     = "EuropeanChampionship"
    EUROPEAN_CHAMPIONSHIP_ITT = "EuropeanChampionshipITT"
    NATIONAL_CHAMPIONSHIP     = "NationalChampionship"
    NATIONAL_CHAMPIONSHIP_ITT = "NationalChampionshipITT"
    TOUR_DE_FRANCE            = "CWTGTFrance"
    OTHER_GRAND_TOUR          = "CWTGTAutres"    # Giro and Vuelta
    MONUMENT                  = "CWTMajeures"
    WORLD_TOUR_CLASSIC_A      = "CWTAutresClasA"
    WORLD_TOUR_CLASSIC_B      = "CWTAutresClasB"
    WORLD_TOUR_CLASSIC_C      = "CWTAutresClasC"
    WORLD_TOUR_STAGE_RACE_A   = "CWTAutresToursA"
    WORLD_TOUR_STAGE_RACE_B   = "CWTAutresToursB"
    WORLD_TOUR_STAGE_RACE_C   = "CWTAutresToursC"
    CONTINENTAL_2_PRO         = "Cont2HC"
    CONTINENTAL_2_1           = "Cont21"
    CONTINENTAL_2_2           = "Cont22"
    CONTINENTAL_1_PRO         = "Cont1HC"
    CONTINENTAL_1_1           = "Cont11"
    CONTINENTAL_1_2           = "Cont12"
    U23_NATIONS_CUP           = "U23_2NCup"
    CONTINENTAL_1_2_U23       = "Cont12U"
    CONTINENTAL_2_2_U23       = "Cont22U"

    @classmethod
    def from_raw(cls, raw: str | None) -> RaceClass | None:
        """Parse a raw PCM constant string, returning None for unknown values."""
        if raw is None:
            return None
        try:
            return cls(raw)
        except ValueError:
            return None


class SquadProfile(enum.Enum):
    """The type of squad to select for a race, derived from its terrain profile."""

    TIME_TRIAL  = "time_trial"
    SPRINT      = "sprint"
    CLIMBING    = "climbing"
    STAGE_RACE  = "stage_race"


class RiderRole(enum.Enum):
    """The role a rider fills within a race squad."""

    DOMESTIQUE          = "domestique"
    FREE                = "free"
    SPRINT_LEAD         = "sprint_lead"
    SPRINT_LEADOUT      = "sprint_leadout"
    CLIMBING_LEAD       = "climbing_lead"
    CLIMBING_DOMESTIQUE = "climbing_domestique"
    TIME_TRIAL          = "time_trial"


@dataclass
class Stage:
    """A single stage imported for a race, carrying terrain metadata."""

    id: int                     # planner DB primary key
    race_id: int                # FK → race.id
    stage_type: Optional[str]   # "Normal", "TimeTrial", "TeamTimeTrial"
    relief: Optional[str]       # "Flat", "Hill", "Medium Mountain", "Mountain"


@dataclass
class Rider:
    """A rider on the player's team, with stats used for race scoring."""

    id: int                 # planner DB primary key
    source_rider_id: int    # original PCM rider ID
    display_name: str
    country: Optional[str] = None  # ISO-style country code from the rider table

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
    country: Optional[str] = None       # host nation code; set for national champs
    race_class: RaceClass | None = None  # None for unrecognised race classes


@dataclass
class RaceDayPenalties:
    """Configurable per-rider race-day band penalties applied to the objective.

    The solver maximises (total score − total penalties).  Penalties push
    riders towards the ``target_min``–``target_max`` band:

    - Days below ``target_min``    → ``under_min_penalty_per_day`` each.
    - Days above ``target_max``    → ``above_target_penalty_per_day`` each
      (up to ``upper_warning``).
    - Days above ``upper_warning`` → ``above_warning_penalty_per_day`` each.
    - ``absolute_max`` is enforced as a hard constraint.
    """

    target_min: int = 60
    target_max: int = 70
    upper_warning: int = 75
    absolute_max: int = 100
    under_min_penalty_per_day: int = 30
    above_target_penalty_per_day: int = 20
    above_warning_penalty_per_day: int = 200


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
    stages: list[Stage] = field(default_factory=list)

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
