"""
Project-wide configuration for the PCM Season Planner optimiser.

Config is loaded from ``config.yaml`` at the workspace root (one level above
this package).  Add new top-level sections to that file and expose them via a
new typed accessor function in this module.

Usage
-----
Import the module and call the accessor for the section you need::

    from optimise import config

    penalties = config.race_day_penalties()

The YAML is loaded once on first import.  Re-import or call ``reload()`` if
you need to pick up changes at runtime (e.g. in tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from optimise.model import RiderRole, SquadProfile

# ---------------------------------------------------------------------------
# Internal loading
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load() -> dict[str, Any]:
    """Read and parse the YAML config file, returning a plain dict."""
    with _CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


_raw: dict[str, Any] = _load()


def reload() -> None:
    """Re-read config.yaml from disk (useful in tests or interactive sessions)."""
    global _raw
    _raw = _load()


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RunConfig:
    """Top-level runtime settings for the optimiser.

    Instances are constructed by :func:`run_config` from config.yaml.
    CLI arguments take precedence and override these values.
    """

    database: str
    time_limit: Optional[float]


@dataclass
class MigrateConfig:
    """File-system paths used by the migration package.

    Instances are constructed by :func:`migrate_config` from config.yaml.
    CLI arguments take precedence and override these values.
    All fields are optional — null in config means the path was not configured.
    """

    lachis_export: Optional[str]
    mod_stages: Optional[str]
    base_stages: Optional[str]
    stage_editor_exe: Optional[str]


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

    Instances are constructed by :func:`race_day_penalties` from config.yaml.
    Do not instantiate directly — config.yaml is the single source of truth.
    """

    target_min: int
    target_max: int
    upper_warning: int
    absolute_max: int
    under_min_penalty_per_day: int
    above_target_penalty_per_day: int
    above_warning_penalty_per_day: int


# ---------------------------------------------------------------------------
# Typed accessors — one function per top-level config section
# ---------------------------------------------------------------------------


def race_day_penalties() -> RaceDayPenalties:
    """Return a :class:`RaceDayPenalties` built from config.yaml.

    Raises ``KeyError`` if a required field is absent from the
    ``race_day_penalties`` section of config.yaml.
    """
    section: dict[str, Any] = _raw.get("race_day_penalties", {})
    return RaceDayPenalties(**section)


def run_config() -> RunConfig:
    """Return a :class:`RunConfig` built from the ``run`` section of config.yaml."""
    section: dict[str, Any] = _raw.get("run", {})
    return RunConfig(
        database=section["database"],
        time_limit=section.get("time_limit"),
    )


def migrate_config() -> MigrateConfig:
    """Return a :class:`MigrateConfig` built from the ``migrate`` section of config.yaml."""
    section: dict[str, Any] = _raw.get("migrate", {})
    return MigrateConfig(
        lachis_export=section.get("lachis_export"),
        mod_stages=section.get("mod_stages"),
        base_stages=section.get("base_stages"),
        stage_editor_exe=section.get("stage_editor_exe"),
    )


def squad_compositions() -> dict[tuple[SquadProfile, int], dict[RiderRole, int]]:
    """Return the squad-composition map built from config.yaml.

    Keys are ``(SquadProfile, squad_size)`` pairs; values are
    ``{RiderRole: count}`` dicts whose counts sum to the squad size.
    """
    section: dict[str, Any] = _raw.get("squad_compositions", {})
    result: dict[tuple[SquadProfile, int], dict[RiderRole, int]] = {}
    for profile_str, sizes in section.items():
        profile = SquadProfile(profile_str)
        for size, roles in sizes.items():
            role_dict = {RiderRole(role_str): count for role_str, count in roles.items()}
            result[(profile, int(size))] = role_dict
    return result
