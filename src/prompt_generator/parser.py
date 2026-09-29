"""Script parser for TXT and DOCX files."""

import logging
import re
from pathlib import Path
from typing import List, Optional

from prompt_generator.models import Scene, SceneStatus

logger = logging.getLogger(__name__)

SCENE_HEADER_PATTERN = re.compile(
    r"^(?:Scene|SCENE|scene)\s+(\d+)[:.]?(.*)$", re.IGNORECASE
)


class ParseError(Exception):
    """Raised when script parsing fails due to syntax or duplicate scenes."""
    pass


def parse_script_text(text: str) -> List[Scene]:
    """Parse raw script text into a list of Scene objects."""
    lines = text.splitlines()
    scenes: List[Scene] = []
    current_number: Optional[int] = None
    current_lines: List[str] = []
    seen_numbers = set()

    for line in lines:
        stripped = line.strip()
        match = SCENE_HEADER_PATTERN.match(stripped)
        if match:
            # Complete previous scene if any
            if current_number is not None:
                scene_content = "\n".join(current_lines).strip()
                scenes.append(Scene(scene_number=current_number, raw_text=scene_content))
                current_lines = []

            new_number = int(match.group(1))
            if new_number in seen_numbers:
                raise ParseError(
                    f"Duplicate scene number detected: {new_number}. "
                    "Scripts must have strictly unique scene numbers."
                )
            seen_numbers.add(new_number)
            current_number = new_number

            remainder = match.group(2).strip()
            if remainder:
                current_lines.append(remainder)
        else:
            if current_number is not None:
                current_lines.append(line)

    # Append the final scene
    if current_number is not None:
        scene_content = "\n".join(current_lines).strip()
        scenes.append(Scene(scene_number=current_number, raw_text=scene_content))

    if not scenes:
        raise ParseError("No valid scenes matching 'Scene <N>' found in script.")

    # Check for non-contiguous sequence warnings (without renumbering)
    numbers = [s.scene_number for s in scenes]
    for i in range(len(numbers) - 1):
        if numbers[i + 1] != numbers[i] + 1:
            logger.warning(
                f"Non-contiguous scene sequence detected between Scene {numbers[i]} "
                f"and Scene {numbers[i+1]}. Original numbering will be strictly preserved."
            )

    return scenes


def parse_docx(file_path: Path) -> List[Scene]:
    """Extract paragraphs and tables from DOCX and parse scenes."""
    try:
        import docx
    except ImportError:
        raise ImportError("python-docx is required to parse DOCX files.")

    doc = docx.Document(file_path)
    full_text_lines: List[str] = []

    for para in doc.paragraphs:
        full_text_lines.append(para.text)

    for table in doc.tables:
        for row in table.rows:
            row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_texts:
                full_text_lines.append(" | ".join(row_texts))

    return parse_script_text("\n".join(full_text_lines))


def parse_script_file(file_path: Path) -> List[Scene]:
    """Parse a script file based on extension (.txt, .docx)."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Script file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".docx":
        return parse_docx(path)
    elif suffix in (".txt", ".md"):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return parse_script_text(f.read())
    else:
        raise ParseError(f"Unsupported file format '{suffix}'. Supported: .txt, .docx")
