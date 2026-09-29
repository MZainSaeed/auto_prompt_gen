"""Tests for instruction file integrity and SHA-256 verification."""

from pathlib import Path
import pytest

from prompt_generator.integrity import (
    CANONICAL_INSTRUCTION_SHA256,
    InstructionIntegrityError,
    calculate_sha256,
    verify_instruction_integrity,
)


def test_canonical_instruction_hash():
    """Verify that the repository's instruction.txt matches the canonical hash."""
    repo_root = Path(__file__).parent.parent
    instruction_file = repo_root / "instruction.txt"
    assert instruction_file.is_file(), "instruction.txt must exist at repo root"

    actual_hash = calculate_sha256(instruction_file)
    assert actual_hash == CANONICAL_INSTRUCTION_SHA256


def test_instruction_verbatim_reading():
    """Verify that instruction text is read in full without truncation."""
    repo_root = Path(__file__).parent.parent
    instruction_file = repo_root / "instruction.txt"

    content = verify_instruction_integrity(instruction_file)
    assert len(content) > 35000
    assert "RULE 0 — THE ZERO-TEXT LOCK" in content


def test_instruction_mutation_failure(tmp_path):
    """Verify that modifying even 1 byte raises InstructionIntegrityError."""
    fake_instr = tmp_path / "mutated_instruction.txt"
    fake_instr.write_text("RULE 0 — THE ZERO-TEXT LOCK (tampered)", encoding="utf-8")

    with pytest.raises(InstructionIntegrityError) as exc_info:
        verify_instruction_integrity(fake_instr, CANONICAL_INSTRUCTION_SHA256)

    assert "INSTRUCTION_INTEGRITY_ERROR" in str(exc_info.value)
    assert "Automated repair is forbidden" in str(exc_info.value)


def test_missing_instruction_file(tmp_path):
    """Verify that a missing instruction file raises InstructionIntegrityError."""
    missing = tmp_path / "non_existent.txt"
    with pytest.raises(InstructionIntegrityError):
        verify_instruction_integrity(missing)
