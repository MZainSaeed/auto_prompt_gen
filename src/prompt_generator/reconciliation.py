"""Reconciliation engine for ordering and verifying prompt results."""

from typing import Dict, List

from prompt_generator.models import Scene, SceneStatus


class OutputIntegrityError(Exception):
    """Raised when output fails reconciliation, missing scenes, or duplicate scenes."""
    pass


def reconcile_scenes(
    expected_scenes: List[Scene], returned_scenes: List[Scene]
) -> List[Scene]:
    """Reconcile returned scenes against expected scenes.

    Enforces:
    1. All expected scene numbers must be present.
    2. Zero unexpected scene numbers.
    3. Prompts must be non-empty strings.
    4. Deterministic sorting strictly by canonical scene_number ascending.
    5. Never renumbers scenes and never assumes contiguous numbering (gaps are preserved).
    """
    expected_ids = {s.scene_number for s in expected_scenes}
    returned_by_id: Dict[int, Scene] = {}

    for s in returned_scenes:
        if s.scene_number in returned_by_id:
            raise OutputIntegrityError(
                f"Duplicate scene {s.scene_number} returned in model output."
            )
        if s.scene_number not in expected_ids:
            raise OutputIntegrityError(
                f"Unexpected scene {s.scene_number} returned by model (not in input script)."
            )
        if not s.generated_prompt or not s.generated_prompt.strip():
            raise OutputIntegrityError(
                f"Empty prompt returned for Scene {s.scene_number}."
            )
        returned_by_id[s.scene_number] = s

    # Check for missing scenes
    missing_ids = expected_ids - set(returned_by_id.keys())
    if missing_ids:
        raise OutputIntegrityError(
            f"OUTPUT_INTEGRITY_ERROR: {len(missing_ids)} scene(s) missing from model output: "
            f"{sorted(list(missing_ids))}"
        )

    # Sort strictly by canonical scene_number ascending without renumbering
    sorted_scenes = sorted(returned_by_id.values(), key=lambda x: x.scene_number)
    return sorted_scenes
