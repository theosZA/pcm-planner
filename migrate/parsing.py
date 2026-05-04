"""
XML parsing helpers and value type coercion for the PCM Lachis export format.

This module has two related concerns kept together because they are both small
and always used as a pair:

XML utilities
    - parse_xml_rows(): memory-efficient streaming row parser for Lachis XML files.
    - text_at() / int_at() / float_at() / count_children(): helpers for reading
      values out of Stage Editor XML elements by XPath.

Type coercion
    - clean_text(), to_int(), to_float(), to_bool_int(), to_iso_date(),
      clean_variant_name(): convert raw XML text to typed Python values, handling
      the quirks of PCM's exported format (commas as decimal separators, 8-digit
      dates encoded as integers, file extensions embedded in variant names, etc.).

Domain converters
    - normalise_level_from_race_class(): maps a PCM race-class constant to a
      human-readable level string.
    - calculate_age_from_birthdate(): derives rider age from a YYYYMMDD integer.
    - read_game_date(): reads the current in-game date from GAM_config.xml.
    - read_player_team(): reads the player's team ID and display name from GAM_user.xml.
"""

from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# XML streaming parser
# ---------------------------------------------------------------------------

def strip_namespace(tag: str) -> str:
    """Remove an XML namespace prefix from a tag string, e.g. '{ns}Tag' → 'Tag'."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def parse_xml_rows(xml_path: Path, row_tag: str) -> Iterable[dict[str, str]]:
    """Stream rows from a Lachis XML file, yielding one dict per matching element.

    Uses iterparse so large files are not loaded into memory all at once.
    Each yielded dict maps child tag names (namespace-stripped) to their text
    content. Missing or empty text values are returned as empty strings.

    Raises FileNotFoundError if xml_path does not exist.
    """
    if not xml_path.exists():
        raise FileNotFoundError(f"Missing XML file: {xml_path}")

    for _event, elem in ET.iterparse(xml_path, events=("end",)):
        if strip_namespace(elem.tag) != row_tag:
            continue

        row: dict[str, str] = {}
        for child in list(elem):
            row[strip_namespace(child.tag)] = child.text or ""

        yield row
        elem.clear()


# ---------------------------------------------------------------------------
# Stage Editor XML element accessors
# ---------------------------------------------------------------------------

def text_at(root: ET.Element, *paths: str) -> str:
    """Return the stripped text of the first matching XPath element, or ''."""
    for path in paths:
        elem = root.find(path)
        if elem is not None and elem.text is not None:
            return elem.text.strip()
    return ""


def int_at(root: ET.Element, *paths: str) -> Optional[int]:
    """Return the integer value at the first matching XPath element, or None."""
    return to_int(text_at(root, *paths))


def float_at(root: ET.Element, *paths: str) -> Optional[float]:
    """Return the float value at the first matching XPath element, or None."""
    return to_float(text_at(root, *paths))


def count_children(root: ET.Element, path: str, child_name: str) -> int:
    """Return the number of child elements named child_name under path, or 0."""
    elem = root.find(path)
    if elem is None:
        return 0
    return len(elem.findall(child_name))


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------

def clean_text(value: Optional[str]) -> str:
    """Return value stripped of surrounding whitespace, or '' if None."""
    if value is None:
        return ""
    return str(value).strip()


def to_int(value: Optional[str]) -> Optional[int]:
    """Parse value as an integer, returning None for None, empty, or non-numeric input."""
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        return None


def to_float(value: Optional[str]) -> Optional[float]:
    """Parse value as a float, handling comma decimal separators used by some PCM exports."""
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_bool_int(value: Optional[str]) -> Optional[int]:
    """Convert a boolean-ish string to 1, 0, or None.

    Recognises "true"/"1"/"yes" → 1 and "false"/"0"/"no" → 0 (case-insensitive).
    Falls back to to_int() for anything else.
    """
    if value is None:
        return None
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes"}:
        return 1
    if text in {"0", "false", "no"}:
        return 0
    return to_int(value)


def to_iso_date(value: Optional[str]) -> str:
    """Convert an 8-digit YYYYMMDD integer string to an ISO-8601 date (YYYY-MM-DD).

    If value is not an 8-digit all-numeric string it is returned unchanged.
    """
    text = clean_text(value)
    if len(text) == 8 and text.isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text


def clean_variant_name(value: Optional[str]) -> str:
    """Strip a known file extension from a PCM stage variant name.

    PCM stores variant names both with and without extensions in different fields.
    This normalises to the bare name without extension so lookups are consistent.
    """
    text = clean_text(value)
    for suffix in (".cds", ".cdx", ".zces", ".xml"):
        if text.casefold().endswith(suffix):
            return text[: -len(suffix)]
    return text


# ---------------------------------------------------------------------------
# Domain converters
# ---------------------------------------------------------------------------

def normalise_level_from_race_class(constant_key: str) -> str:
    """Map a PCM race-class CONSTANT string to a planner level label.

    This mapping is deliberately conservative. Improve once all race_class
    constants have been inspected.
    """
    key = clean_text(constant_key).casefold()

    if "grandtour" in key or "gt" in key:
        return "grand_tour"
    if "world" in key or "wt" in key:
        return "world_tour"
    if "pro" in key:
        return "pro"
    if "1" in key:
        return "class_1"
    if "2" in key:
        return "class_2"

    return constant_key or "unknown"


def read_game_date(lachis_export: Path) -> datetime.date:
    """Read the current in-game date from GAM_config.xml.

    GAM_config.xml contains two rows: a real data row (IDconfig != 0) and a
    help/template row (IsHelpRow = "true"). The date is stored as a YYYYMMDD
    integer in gene_i_date on the real row.

    Raises ValueError if no valid game date can be found.
    """
    config_xml = lachis_export / "GAM_config.xml"

    for row in parse_xml_rows(config_xml, "GAM_config"):
        if row.get("IsHelpRow", "").strip().casefold() == "true":
            continue

        date_raw = to_int(row.get("gene_i_date"))
        if not date_raw:
            continue

        text = str(date_raw)
        if len(text) != 8:
            raise ValueError(f"Unexpected gene_i_date format: {text!r}")

        try:
            return datetime.date(int(text[0:4]), int(text[4:6]), int(text[6:8]))
        except ValueError as exc:
            raise ValueError(f"Cannot parse game date from {text!r}: {exc}") from exc

    raise ValueError("No valid game date found in GAM_config.xml")


def read_player_team(lachis_export: Path) -> tuple[int, str]:
    """Read the player's team ID and display name from GAM_user.xml.

    GAM_user.xml contains one row per user slot. The active human player has
    game_i_active = 1. The player's team is stored in fkIDteam_duplicate and
    their Steam/game display name in game_sz_display_name.

    Returns (source_team_id, display_name).
    Raises ValueError if no active player row can be found.
    """
    user_xml = lachis_export / "GAM_user.xml"

    for row in parse_xml_rows(user_xml, "GAM_user"):
        if to_int(row.get("game_i_active")) != 1:
            continue

        source_team_id = to_int(row.get("fkIDteam_duplicate"))
        display_name = clean_text(row.get("game_sz_display_name"))

        if source_team_id is None or source_team_id == 0:
            raise ValueError(
                f"Active player row found but fkIDteam_duplicate is missing or zero "
                f"(display_name={display_name!r})"
            )

        return source_team_id, display_name

    raise ValueError("No active player row found in GAM_user.xml")


def load_country_iso_lookup(lachis_export: Path) -> dict[int, str]:
    """Build a mapping from country ID to ISO country code (lowercase).

    Reads STA_country.xml and returns dict[country_id, iso_code] where
    iso_code is the CONSTANT field normalised to lowercase.
    """
    country_to_iso: dict[int, str] = {}
    for row in parse_xml_rows(lachis_export / "STA_country.xml", "STA_country"):
        country_id = to_int(row.get("IDcountry"))
        iso_code = clean_text(row.get("CONSTANT")).lower()
        if country_id is not None and iso_code:
            country_to_iso[country_id] = iso_code
    return country_to_iso


def load_country_lookup(lachis_export: Path) -> dict[int, str]:
    """Build a mapping from region ID to ISO country code (lowercase).

    Reads STA_region.xml to map region_id → country_id, then uses
    load_country_iso_lookup for country_id → iso_code. Returns a combined
    dict[region_id, iso_code].
    """
    country_to_iso = load_country_iso_lookup(lachis_export)

    region_to_country: dict[int, int] = {}
    for row in parse_xml_rows(lachis_export / "STA_region.xml", "STA_region"):
        region_id = to_int(row.get("IDregion"))
        country_id = to_int(row.get("fkIDcountry"))
        if region_id is not None and country_id is not None:
            region_to_country[region_id] = country_id

    return {
        region_id: country_to_iso[country_id]
        for region_id, country_id in region_to_country.items()
        if country_id in country_to_iso
    }


def calculate_age_from_birthdate(
    birthdate_raw: Optional[int],
    game_date: Optional[datetime.date],
) -> Optional[int]:
    """Derive exact rider age from a PCM YYYYMMDD-encoded birthdate integer.

    PCM stores birthdates as integers like 19950314 (YYYYMMDD). Age is computed
    exactly using the in-game date, accounting for whether the rider's birthday
    has already occurred in the current year.

    Returns None if either argument is absent or the birthdate cannot be parsed.
    """
    if birthdate_raw is None or game_date is None:
        return None

    text = str(birthdate_raw)
    if len(text) != 8:
        return None

    try:
        birth_date = datetime.date(int(text[0:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None

    return game_date.year - birth_date.year - (
        (game_date.month, game_date.day) < (birth_date.month, birth_date.day)
    )
