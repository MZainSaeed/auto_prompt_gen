"""Instruction file integrity verification."""

import hashlib
from pathlib import Path

CANONICAL_INSTRUCTION_SHA256 = (
    "1E8B4FE8F11C1B0625889855C765040E96761758735B32C4EC20E41301BDC007".lower()
)


class InstructionIntegrityError(Exception):
    """Raised when instruction.txt fails SHA-256 validation."""
    pass


def calculate_sha256(file_path: Path) -> str:
    """Calculate the SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest().lower()


def verify_instruction_integrity(
    file_path: Path, expected_hash: str = CANONICAL_INSTRUCTION_SHA256
) -> str:
    """Verify that the instruction file matches the canonical SHA-256 hash.

    Returns the verbatim text if valid.
    Raises InstructionIntegrityError if invalid or missing.
    Never attempts automated repair.
    """
    path = Path(file_path)
    if not path.is_file():
        raise InstructionIntegrityError(f"Instruction file not found at: {path}")

    actual_hash = calculate_sha256(path)
    if actual_hash != expected_hash.lower():
        raise InstructionIntegrityError(
            f"INSTRUCTION_INTEGRITY_ERROR: Hash mismatch for {path}. "
            f"Expected {expected_hash.lower()}, got {actual_hash}. "
            "Automated repair is forbidden. Restore instruction.txt from source control."
        )

    with open(path, "r", encoding="utf-8") as f:
        return f.read()
