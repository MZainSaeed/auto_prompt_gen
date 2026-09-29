"""Tests for script parsing (TXT, DOCX, regex matching, duplicate validation)."""

import pytest
from prompt_generator.parser import ParseError, parse_script_text


def test_parse_valid_scenes_with_case_variations():
    """Verify parsing handles 'Scene', 'scene', 'SCENE' at line start."""
    script = """
    Scene 1: Exterior castle at night. Heavy fog and ancient stone gargoyles.
    The moonlight glints off the moat.

    scene 2: Interior throne room.
    King sitting on throne in deep thought.

    SCENE 3: Courtyard battle.
    Soldiers clashing swords in torrential rain.
    """
    scenes = parse_script_text(script)
    assert len(scenes) == 3
    assert scenes[0].scene_number == 1
    assert "Exterior castle at night" in scenes[0].raw_text
    assert "moonlight glints" in scenes[0].raw_text
    assert scenes[1].scene_number == 2
    assert "King sitting on throne" in scenes[1].raw_text
    assert scenes[2].scene_number == 3
    assert "Courtyard battle" in scenes[2].raw_text


def test_reject_duplicate_scene_numbers():
    """Verify that duplicate scene numbers trigger ParseError."""
    script = """
    Scene 1: First scene.
    Scene 2: Second scene.
    Scene 1: Duplicate of first scene!
    """
    with pytest.raises(ParseError) as exc:
        parse_script_text(script)
    assert "Duplicate scene number detected: 1" in str(exc.value)


def test_non_contiguous_sequence_preservation():
    """Verify that missing sequence numbers (e.g., 1, 2, 4, 5) are preserved."""
    script = """
    Scene 1: Scene one.
    Scene 2: Scene two.
    Scene 4: Scene four (notice 3 is missing).
    Scene 5: Scene five.
    """
    scenes = parse_script_text(script)
    assert len(scenes) == 4
    assert [s.scene_number for s in scenes] == [1, 2, 4, 5]


def test_ignore_inline_scene_mentions():
    """Verify that 'scene 1' embedded inside text is not parsed as a new header."""
    script = """
    Scene 1: The detective enters the room. He says, as we saw in scene 99, the killer is here.
    He points at the suspect.
    """
    scenes = parse_script_text(script)
    assert len(scenes) == 1
    assert scenes[0].scene_number == 1
    assert "as we saw in scene 99" in scenes[0].raw_text
