"""
Stage file resolution and Stage Editor metadata export for the PCM Season Planner.

Responsibilities:
- StageResolution: dataclass describing the outcome of resolving a stage variant
  name to a concrete .cds file path.
- build_file_index() / find_indexed_file(): build case-insensitive filename
  lookup tables for the mod and base-game Stages folders.
- parse_cdx_fallback(): read a .cdx redirect file to find the fallback variant.
- resolve_stage_file(): walk the CDX fallback chain (up to 8 levels deep) to
  find the .cds file for a given stage variant.
- export_stage_editor_xml(): invoke CTStageEditor.exe -exportStageData in
  batches, reusing cached XMLs by default to avoid slow re-exports.
- parse_stage_editor_xml(): extract all metadata fields from a Stage Editor
  export XML file.
- update_stages_with_stage_editor_metadata(): orchestrates resolution, export,
  and DB update for all stage rows in a single import run.
"""

from __future__ import annotations

import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

from migrate.parsing import (
    clean_text,
    clean_variant_name,
    count_children,
    float_at,
    int_at,
    text_at,
)


# ---------------------------------------------------------------------------
# Stage resolution result
# ---------------------------------------------------------------------------

@dataclass
class StageResolution:
    """Outcome of resolving a stage variant name to a .cds file.

    status values:
    - "direct_cds"          — .cds found directly for the original variant.
    - "cds_via_cdx_fallback"— .cds found after following one or more CDX redirects.
    - "missing"             — no .cds or .cdx file found at all.
    - "cdx_without_fallback"— a .cdx was found but it contained no <Fallback> entry.
    - "error"               — CDX fallback loop detected, or depth limit exceeded.

    cds_source / cdx_source are "mod" or "base", indicating which Stages folder
    the file came from (mod takes priority over base game).
    """
    status: str
    original_variant: str
    resolved_variant: str
    cds_path: str = field(default="")
    cds_source: str = field(default="")
    cdx_path: str = field(default="")
    cdx_source: str = field(default="")
    fallback_variant: str = field(default="")
    cdx_stage_name: str = field(default="")
    cdx_region_id: str = field(default="")
    error: str = field(default="")


# ---------------------------------------------------------------------------
# File index helpers
# ---------------------------------------------------------------------------

def build_file_index(folder: Path, suffix: str) -> dict[str, Path]:
    """Recursively index all files with the given suffix under folder.

    Returns a dict mapping lowercase filename → absolute Path. If folder does
    not exist, an empty dict is returned.
    """
    index: dict[str, Path] = {}
    if not folder.exists():
        return index
    for path in folder.rglob(f"*{suffix}"):
        if path.is_file():
            index[path.name.casefold()] = path
    return index


def find_indexed_file(
    variant: str,
    suffix: str,
    mod_index: dict[str, Path],
    base_index: dict[str, Path],
) -> tuple[Optional[Path], str]:
    """Look up a variant+suffix in the mod index, falling back to the base index.

    Returns (path, source) where source is "mod", "base", or "" (not found).
    """
    filename = f"{clean_variant_name(variant)}{suffix}".casefold()
    if filename in mod_index:
        return mod_index[filename], "mod"
    if filename in base_index:
        return base_index[filename], "base"
    return None, ""


# ---------------------------------------------------------------------------
# CDX redirect parsing and stage file resolution
# ---------------------------------------------------------------------------

def parse_cdx_fallback(cdx_path: Path) -> tuple[str, str, str]:
    """Parse a .cdx redirect file and return (fallback_variant, stage_name, region_id).

    .cdx files are small XML documents that point to a fallback .cds variant
    and optionally embed a stage name and region ID.
    """
    root = ET.parse(cdx_path).getroot()
    fallback = ""
    stage_name = ""
    region_id = ""

    for child in list(root):
        tag = child.tag.casefold()
        value = clean_text(child.text)
        if tag == "fallback":
            fallback = clean_variant_name(value)
        elif tag == "stagename":
            stage_name = value
        elif tag == "regionid":
            region_id = value

    return fallback, stage_name, region_id


def resolve_stage_file(
    variant: str,
    mod_cds_index: dict[str, Path],
    base_cds_index: dict[str, Path],
    mod_cdx_index: dict[str, Path],
    base_cdx_index: dict[str, Path],
) -> StageResolution:
    """Resolve a stage variant name to a .cds file, following CDX redirects as needed.

    Search order at each step:
      1. mod .cds  2. base .cds  3. mod .cdx  4. base .cdx  → follow fallback

    Stops after 8 redirect hops to guard against infinite loops.
    The returned StageResolution records the first CDX encountered (if any) even
    when the final .cds is found further down the chain.
    """
    original_variant = clean_variant_name(variant)
    current_variant = original_variant

    first_cdx_path = ""
    first_cdx_source = ""
    first_fallback_variant = ""
    first_cdx_stage_name = ""
    first_cdx_region_id = ""

    seen: set[str] = set()

    for _depth in range(8):
        if current_variant in seen:
            return StageResolution(
                status="error",
                original_variant=original_variant,
                resolved_variant=current_variant,
                error=f"CDX fallback loop at {current_variant}",
                cdx_path=first_cdx_path,
                cdx_source=first_cdx_source,
                fallback_variant=first_fallback_variant,
                cdx_stage_name=first_cdx_stage_name,
                cdx_region_id=first_cdx_region_id,
            )

        seen.add(current_variant)

        cds_path, cds_source = find_indexed_file(
            current_variant, ".cds", mod_cds_index, base_cds_index
        )
        if cds_path:
            return StageResolution(
                status=(
                    "direct_cds"
                    if current_variant == original_variant
                    else "cds_via_cdx_fallback"
                ),
                original_variant=original_variant,
                resolved_variant=current_variant,
                cds_path=str(cds_path),
                cds_source=cds_source,
                cdx_path=first_cdx_path,
                cdx_source=first_cdx_source,
                fallback_variant=first_fallback_variant,
                cdx_stage_name=first_cdx_stage_name,
                cdx_region_id=first_cdx_region_id,
            )

        cdx_path, cdx_source = find_indexed_file(
            current_variant, ".cdx", mod_cdx_index, base_cdx_index
        )
        if not cdx_path:
            return StageResolution(
                status="missing",
                original_variant=original_variant,
                resolved_variant=current_variant,
                error=f"No .cds or .cdx found for {current_variant}",
                cdx_path=first_cdx_path,
                cdx_source=first_cdx_source,
                fallback_variant=first_fallback_variant,
                cdx_stage_name=first_cdx_stage_name,
                cdx_region_id=first_cdx_region_id,
            )

        fallback_variant, cdx_stage_name, cdx_region_id = parse_cdx_fallback(cdx_path)

        if not first_cdx_path:
            first_cdx_path = str(cdx_path)
            first_cdx_source = cdx_source
            first_fallback_variant = fallback_variant
            first_cdx_stage_name = cdx_stage_name
            first_cdx_region_id = cdx_region_id

        if not fallback_variant:
            return StageResolution(
                status="cdx_without_fallback",
                original_variant=original_variant,
                resolved_variant=current_variant,
                error=f".cdx found but no fallback in {cdx_path}",
                cdx_path=first_cdx_path,
                cdx_source=first_cdx_source,
                fallback_variant=first_fallback_variant,
                cdx_stage_name=first_cdx_stage_name,
                cdx_region_id=first_cdx_region_id,
            )

        current_variant = fallback_variant

    return StageResolution(
        status="error",
        original_variant=original_variant,
        resolved_variant=current_variant,
        error=f"CDX fallback depth exceeded for {original_variant}",
        cdx_path=first_cdx_path,
        cdx_source=first_cdx_source,
        fallback_variant=first_fallback_variant,
        cdx_stage_name=first_cdx_stage_name,
        cdx_region_id=first_cdx_region_id,
    )


# ---------------------------------------------------------------------------
# Stage Editor export
# ---------------------------------------------------------------------------

def _batch(items: Sequence[Path], size: int) -> Iterable[list[Path]]:
    """Yield successive slices of items with at most size elements each."""
    for index in range(0, len(items), size):
        yield list(items[index : index + size])


def export_stage_editor_xml(
    stage_editor_exe: Path,
    cds_paths: list[Path],
    batch_size: int = 80,
    force_export: bool = False,
) -> Path:
    """Invoke CTStageEditor.exe -exportStageData to produce per-stage XML files.

    By default, any .cds path that already has a matching XML in ExportStageData/
    is skipped — the cached XML is reused as-is. This makes repeated runs fast
    because stage file content almost never changes.

    Set force_export=True to delete all cached XMLs and re-export everything.
    Use this if the underlying .cds stage files have actually been updated.

    The Stage Editor exe is only required (and validated) when there are files
    that actually need exporting. If all XMLs are cached, the exe is never
    accessed.

    Returns the ExportStageData directory path.
    """
    stage_editor_dir = stage_editor_exe.parent
    export_dir = stage_editor_dir / "ExportStageData"
    export_dir.mkdir(parents=True, exist_ok=True)

    unique_paths = sorted({path.resolve() for path in cds_paths})

    if force_export:
        # Remove existing XMLs so everything is freshly regenerated.
        for cds_path in unique_paths:
            xml_path = export_dir / f"{cds_path.stem}.xml"
            if xml_path.exists():
                xml_path.unlink()
        paths_to_export = unique_paths
    else:
        # Only export paths that do not already have a cached XML.
        paths_to_export = [
            p for p in unique_paths
            if not (export_dir / f"{p.stem}.xml").exists()
        ]

    cached_count = len(unique_paths) - len(paths_to_export)
    if cached_count:
        print(f"  Reusing {cached_count} cached stage XML file(s) (use --force-stage-export to re-export).")

    if not paths_to_export:
        return export_dir

    if not stage_editor_exe.exists():
        raise FileNotFoundError(f"Stage Editor executable not found: {stage_editor_exe}")

    print(f"  Exporting {len(paths_to_export)} stage file(s) via CTStageEditor.exe...")
    for group in _batch(paths_to_export, batch_size):
        command = [str(stage_editor_exe), "-exportStageData", *[str(p) for p in group]]
        subprocess.run(command, cwd=stage_editor_dir, check=True)

    return export_dir


# ---------------------------------------------------------------------------
# Stage Editor XML parsing
# ---------------------------------------------------------------------------

def parse_stage_editor_xml(xml_path: Path) -> dict[str, object]:
    """Parse a Stage Editor export XML file and return a dict of stage metadata fields."""
    root = ET.parse(xml_path).getroot()

    return {
        "stage_name": text_at(root, "Name"),
        "region_name": text_at(root, "RegionName"),
        "region_id": int_at(root, "RegionId"),

        "stage_type": text_at(root, "Type"),
        "relief": text_at(root, "Relief"),

        "cobblestone_difficulty_ratio": float_at(
            root,
            "CobblestonesDifficulty/Ratio",
            "CobblestoneDifficulty/Ratio",
        ),
        "cobblestone_difficulty_type": int_at(
            root,
            "CobblestonesDifficulty/Type",
            "CobblestoneDifficulty/Type",
        ),

        "dirt_road_difficulty_ratio": float_at(root, "DirtRoadDifficulty/Ratio"),
        "dirt_road_difficulty_type": int_at(root, "DirtRoadDifficulty/Type"),

        "spline_length_km": float_at(root, "SplineLength"),
        "race_length_km": float_at(root, "RaceLength"),

        "elevation_total_m": float_at(root, "Elevation/Total"),
        "elevation_second_half_m": float_at(root, "Elevation/SecondHalf"),
        "elevation_last_20km_m": float_at(root, "Elevation/Last20Km"),
        "elevation_last_3km_m": float_at(root, "Elevation/Last3Km"),
        "elevation_last_1km_m": float_at(root, "Elevation/Last1Km"),

        "uphill_sprint": float_at(root, "UpHillSprint"),
        "time_gap": int_at(root, "TimeGap"),
        "gene_f_mountain": float_at(root, "Gene_f_Mountain"),

        "altitude_max_m": float_at(root, "Altitude/Max"),
        "altitude_start_line_m": float_at(root, "Altitude/StartLine"),
        "altitude_finish_line_m": float_at(root, "Altitude/FinishLine"),

        "max_local_slope": float_at(root, "MaxLocalSlope"),

        "cumulated_pavement_km": float_at(root, "CumulatedPavement"),
        "cumulated_dirt_road_km": float_at(root, "CumulatedDirtRoad"),
        "cumulated_climbing_km": float_at(root, "CumulatedClimbing"),

        "last_summit_position_km": float_at(root, "LastSummit/Position"),
        "last_summit_ascension_length_before_km": float_at(root, "LastSummit/AscensionLengthBefore"),
        "last_summit_ascension_slope_before": float_at(root, "LastSummit/AscensionSlopeBefore"),
        "last_summit_ascension_denivele_before_m": float_at(root, "LastSummit/AscensionDeniveleBefore"),

        "wind_force": int_at(root, "WindForce"),

        "sprint_count": count_children(root, "Sprints", "Sprint"),
        "pavement_count": count_children(root, "Pavements", "Pavement"),
        "dirt_road_count": count_children(root, "DirtRoads", "DirtRoad"),
    }


# ---------------------------------------------------------------------------
# DB update orchestrator
# ---------------------------------------------------------------------------

def update_stages_with_stage_editor_metadata(
    conn: sqlite3.Connection,
    stage_rows: list[dict[str, object]],
    mod_stages: Path,
    base_stages: Path,
    stage_editor_exe: Path,
    force_export: bool = False,
) -> tuple[int, int, int]:
    """Resolve stage files and update stage rows with Stage Editor XML metadata.

    For each stage row (containing source_stage_id and variant), resolves the
    variant to a .cds file, exports stage metadata XML via CTStageEditor.exe
    (reusing cached XMLs unless force_export is True), parses each XML, and
    writes all metadata fields back to the stage table.

    Returns (stages_updated, missing_stage_files, missing_exported_xml).
    - stages_updated: rows successfully updated with metadata.
    - missing_stage_files: stages where no .cds/.cdx could be found.
    - missing_exported_xml: stages where the Stage Editor did not produce an XML.
    """
    mod_cds_index = build_file_index(mod_stages, ".cds")
    base_cds_index = build_file_index(base_stages, ".cds")
    mod_cdx_index = build_file_index(mod_stages, ".cdx")
    base_cdx_index = build_file_index(base_stages, ".cdx")

    resolutions: dict[int, StageResolution] = {}
    cds_paths: list[Path] = []
    missing = 0

    for stage in stage_rows:
        source_stage_id = int(stage["source_stage_id"])
        variant = str(stage["variant"])

        resolution = resolve_stage_file(
            variant=variant,
            mod_cds_index=mod_cds_index,
            base_cds_index=base_cds_index,
            mod_cdx_index=mod_cdx_index,
            base_cdx_index=base_cdx_index,
        )
        resolutions[source_stage_id] = resolution

        if resolution.cds_path:
            cds_paths.append(Path(resolution.cds_path))
        else:
            missing += 1

    export_dir = export_stage_editor_xml(
        stage_editor_exe=stage_editor_exe,
        cds_paths=cds_paths,
        force_export=force_export,
    )

    updated = 0
    xml_missing = 0

    for source_stage_id, resolution in resolutions.items():
        if not resolution.cds_path:
            continue

        cds_path = Path(resolution.cds_path)
        xml_path = export_dir / f"{cds_path.stem}.xml"

        if not xml_path.exists():
            xml_missing += 1
            continue

        parsed = parse_stage_editor_xml(xml_path)

        conn.execute(
            """
            UPDATE stage
            SET
                resolved_variant = ?,
                cds_source = ?,
                cds_path = ?,
                cdx_path = ?,
                stage_metadata_source = ?,
                stage_metadata_xml_path = ?,

                stage_name = ?,
                region_id = ?,
                region_name = ?,

                stage_type = ?,
                relief = ?,

                race_length_km = ?,
                spline_length_km = ?,

                elevation_total_m = ?,
                elevation_second_half_m = ?,
                elevation_last_20km_m = ?,
                elevation_last_3km_m = ?,
                elevation_last_1km_m = ?,

                uphill_sprint = ?,
                time_gap = ?,
                gene_f_mountain = ?,

                altitude_max_m = ?,
                altitude_start_line_m = ?,
                altitude_finish_line_m = ?,

                max_local_slope = ?,

                cumulated_pavement_km = ?,
                cumulated_dirt_road_km = ?,
                cumulated_climbing_km = ?,

                cobblestone_difficulty_ratio = ?,
                cobblestone_difficulty_type = ?,
                dirt_road_difficulty_ratio = ?,
                dirt_road_difficulty_type = ?,

                last_summit_position_km = ?,
                last_summit_ascension_length_before_km = ?,
                last_summit_ascension_slope_before = ?,
                last_summit_ascension_denivele_before_m = ?,

                wind_force = ?,

                sprint_count = ?,
                pavement_count = ?,
                dirt_road_count = ?
            WHERE source_stage_id = ?;
            """,
            (
                resolution.resolved_variant,
                resolution.cds_source,
                resolution.cds_path,
                resolution.cdx_path,
                "stage_editor_xml",
                str(xml_path),

                parsed["stage_name"],
                parsed["region_id"],
                parsed["region_name"],

                parsed["stage_type"],
                parsed["relief"],

                parsed["race_length_km"],
                parsed["spline_length_km"],

                parsed["elevation_total_m"],
                parsed["elevation_second_half_m"],
                parsed["elevation_last_20km_m"],
                parsed["elevation_last_3km_m"],
                parsed["elevation_last_1km_m"],

                parsed["uphill_sprint"],
                parsed["time_gap"],
                parsed["gene_f_mountain"],

                parsed["altitude_max_m"],
                parsed["altitude_start_line_m"],
                parsed["altitude_finish_line_m"],

                parsed["max_local_slope"],

                parsed["cumulated_pavement_km"],
                parsed["cumulated_dirt_road_km"],
                parsed["cumulated_climbing_km"],

                parsed["cobblestone_difficulty_ratio"],
                parsed["cobblestone_difficulty_type"],
                parsed["dirt_road_difficulty_ratio"],
                parsed["dirt_road_difficulty_type"],

                parsed["last_summit_position_km"],
                parsed["last_summit_ascension_length_before_km"],
                parsed["last_summit_ascension_slope_before"],
                parsed["last_summit_ascension_denivele_before_m"],

                parsed["wind_force"],

                parsed["sprint_count"],
                parsed["pavement_count"],
                parsed["dirt_road_count"],

                source_stage_id,
            ),
        )
        updated += 1

    return updated, missing, xml_missing
