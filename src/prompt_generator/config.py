"""Configuration loading, validation, and immutability locks."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from prompt_generator.integrity import (
    CANONICAL_INSTRUCTION_SHA256,
    InstructionIntegrityError,
    verify_instruction_integrity,
)

LOCKED_MODEL = "gemini-3.1-pro-high"
LOCKED_EFFORT = "high"
LOCKED_BATCH_SIZE = 15
LOCKED_PROVIDER = "antigravity_cli"
LOCKED_INPUT_FORMAT = "stream-json"
LOCKED_OUTPUT_FORMAT = "stream-json"
LOCKED_PRINT_TIMEOUT = "10m"


class ConfigValidationError(Exception):
    """Raised when configuration violates policy locks."""
    pass


@dataclass(frozen=True)
class PromptGeneratorConfig:
    provider: str
    executable: str
    model: str
    effort: str
    batch_size: int
    print_timeout: str
    timeout_minutes: int
    max_retries: int
    input_format: str
    output_format: str
    json_schema_file: Path
    instruction_file: Path
    instruction_sha256: str
    instruction_text: str

    @classmethod
    def load(cls, config_path: Path, base_dir: Path = None) -> "PromptGeneratorConfig":
        """Load and validate configuration against strict system policies."""
        path = Path(config_path)
        if not path.is_file():
            raise ConfigValidationError(f"Configuration file not found: {path}")

        if base_dir is None:
            base_dir = path.parent.parent

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        pg_cfg = data.get("prompt_generator")
        if not pg_cfg:
            raise ConfigValidationError("Missing 'prompt_generator' root key in configuration.")

        # Strict Policy Locks
        provider = pg_cfg.get("provider", LOCKED_PROVIDER)
        if provider != LOCKED_PROVIDER:
            raise ConfigValidationError(
                f"Invalid provider '{provider}'. Only '{LOCKED_PROVIDER}' is supported."
            )

        model = pg_cfg.get("model", LOCKED_MODEL)
        if model != LOCKED_MODEL:
            raise ConfigValidationError(
                f"Invalid model '{model}'. STRICT POLICY: Only '{LOCKED_MODEL}' is permitted. "
                "No fallbacks allowed."
            )

        effort = pg_cfg.get("effort", LOCKED_EFFORT)
        if effort != LOCKED_EFFORT:
            raise ConfigValidationError(
                f"Invalid effort '{effort}'. STRICT POLICY: Only '{LOCKED_EFFORT}' is permitted. "
                "No downgrades allowed."
            )

        batch_size = pg_cfg.get("batch_size", LOCKED_BATCH_SIZE)
        if batch_size != LOCKED_BATCH_SIZE:
            raise ConfigValidationError(
                f"Invalid batch size {batch_size}. LOCKED POLICY: batch_size must be exactly {LOCKED_BATCH_SIZE}."
            )

        input_format = pg_cfg.get("input_format", LOCKED_INPUT_FORMAT)
        if input_format != LOCKED_INPUT_FORMAT:
            raise ConfigValidationError(
                f"Invalid input_format '{input_format}'. Must be '{LOCKED_INPUT_FORMAT}'."
            )

        output_format = pg_cfg.get("output_format", LOCKED_OUTPUT_FORMAT)
        if output_format != LOCKED_OUTPUT_FORMAT:
            raise ConfigValidationError(
                f"Invalid output_format '{output_format}'. Must be paired with '{LOCKED_OUTPUT_FORMAT}'."
            )

        print_timeout = pg_cfg.get("print_timeout", LOCKED_PRINT_TIMEOUT)
        if print_timeout != LOCKED_PRINT_TIMEOUT:
            raise ConfigValidationError(
                f"Invalid print_timeout '{print_timeout}'. Must be '{LOCKED_PRINT_TIMEOUT}'."
            )

        # Resolve paths
        schema_path = base_dir / pg_cfg.get("json_schema_file", "config/scene_schema.json")
        if not schema_path.is_file():
            raise ConfigValidationError(f"Scene schema file not found at: {schema_path}")

        instr_path = base_dir / pg_cfg.get("instruction_file", "instruction.txt")
        expected_hash = pg_cfg.get("instruction_sha256", CANONICAL_INSTRUCTION_SHA256)

        # Verify instruction file integrity and load verbatim text
        instruction_text = verify_instruction_integrity(instr_path, expected_hash)

        return cls(
            provider=provider,
            executable=pg_cfg.get("executable", "agy"),
            model=model,
            effort=effort,
            batch_size=batch_size,
            print_timeout=print_timeout,
            timeout_minutes=pg_cfg.get("timeout_minutes", 10),
            max_retries=pg_cfg.get("max_retries", 3),
            input_format=input_format,
            output_format=output_format,
            json_schema_file=schema_path,
            instruction_file=instr_path,
            instruction_sha256=expected_hash,
            instruction_text=instruction_text,
        )
