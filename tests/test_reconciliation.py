"""Tests for reconciliation engine, sorting, and non-contiguous sequence preservation."""

from pathlib import Path
import pytest
import docx

from prompt_generator.docx_exporter import export_prompts_to_docx
from prompt_generator.models import Scene, SceneStatus
from prompt_generator.reconciliation import OutputIntegrityError, reconcile_scenes


def test_reconciliation_ordering_out_of_order():
    """Verify that out-of-order batch responses are sorted in canonical ascending order."""
    expected = [
        Scene(scene_number=1, raw_text="text 1"),
        Scene(scene_number=2, raw_text="text 2"),
        Scene(scene_number=3, raw_text="text 3"),
    ]
    returned = [
        Scene(scene_number=3, raw_text="text 3", generated_prompt="Prompt 3"),
        Scene(scene_number=1, raw_text="text 1", generated_prompt="Prompt 1"),
        Scene(scene_number=2, raw_text="text 2", generated_prompt="Prompt 2"),
    ]
    reconciled = reconcile_scenes(expected, returned)
    assert [s.scene_number for s in reconciled] == [1, 2, 3]
    assert [s.generated_prompt for s in reconciled] == ["Prompt 1", "Prompt 2", "Prompt 3"]


def test_non_contiguous_sequence_preservation():
    """Verify that gaps in scene numbers are preserved without renumbering or filling."""
    expected = [
        Scene(scene_number=1, raw_text="text 1"),
        Scene(scene_number=2, raw_text="text 2"),
        Scene(scene_number=4, raw_text="text 4"),
        Scene(scene_number=5, raw_text="text 5"),
    ]
    returned = [
        Scene(scene_number=4, raw_text="text 4", generated_prompt="Prompt 4"),
        Scene(scene_number=1, raw_text="text 1", generated_prompt="Prompt 1"),
        Scene(scene_number=5, raw_text="text 5", generated_prompt="Prompt 5"),
        Scene(scene_number=2, raw_text="text 2", generated_prompt="Prompt 2"),
    ]
    reconciled = reconcile_scenes(expected, returned)
    assert [s.scene_number for s in reconciled] == [1, 2, 4, 5]
    assert [s.generated_prompt for s in reconciled] == ["Prompt 1", "Prompt 2", "Prompt 4", "Prompt 5"]


def test_reconciliation_missing_scene_error():
    """Verify that missing scene raises OutputIntegrityError."""
    expected = [
        Scene(scene_number=1, raw_text="text 1"),
        Scene(scene_number=2, raw_text="text 2"),
    ]
    returned = [
        Scene(scene_number=1, raw_text="text 1", generated_prompt="Prompt 1"),
    ]
    with pytest.raises(OutputIntegrityError) as exc:
        reconcile_scenes(expected, returned)
    assert "OUTPUT_INTEGRITY_ERROR: 1 scene(s) missing" in str(exc.value)


def test_docx_export_formatting(tmp_path):
    """Verify that export_prompts_to_docx writes correct Scene <N>: labels."""
    scenes = [
        Scene(scene_number=1, raw_text="...", generated_prompt="Hand-painted castle in fog."),
        Scene(scene_number=3, raw_text="...", generated_prompt="Ancient dragon over mountains."),
    ]
    out_file = tmp_path / "test_output.docx"
    export_prompts_to_docx(scenes, out_file)

    assert out_file.is_file()
    doc = docx.Document(out_file)
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    assert "Generated Visual Prompts" in paragraphs[0]
    assert paragraphs[1] == "Scene 1: Hand-painted castle in fog."
    assert paragraphs[2] == "Scene 3: Ancient dragon over mountains."
