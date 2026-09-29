"""Tests for configuration loading, policy locks, and validation."""

import json
from pathlib import Path
import pytest

from prompt_generator.config import (
    ConfigValidationError,
    PromptGeneratorConfig,
    LOCKED_MODEL,
    LOCKED_EFFORT,
    LOCKED_BATCH_SIZE,
)


def test_load_canonical_config():
    """Verify that canonical configuration loads and satisfies all locks."""
    repo_root = Path(__file__).parent.parent
    config_path = repo_root / "config" / "prompt_generator_config.json"
    assert config_path.is_file()

    cfg = PromptGeneratorConfig.load(config_path, base_dir=repo_root)
    assert cfg.model == LOCKED_MODEL
    assert cfg.effort == LOCKED_EFFORT
    assert cfg.batch_size == LOCKED_BATCH_SIZE
    assert cfg.print_timeout == "10m"
    assert cfg.input_format == "stream-json"
    assert cfg.output_format == "stream-json"
    assert len(cfg.instruction_text) > 35000


def test_reject_fallback_models(tmp_path):
    """Verify that attempting to switch models raises ConfigValidationError."""
    repo_root = Path(__file__).parent.parent
    for illegal_model in ["gemini-3.8-flash", "gemini-2.5-pro", "gemini-2.5-flash", "claude-3-5-sonnet", "gpt-4o"]:
        bad_cfg = tmp_path / f"config_{illegal_model}.json"
        data = {
            "prompt_generator": {
                "provider": "antigravity_cli",
                "model": illegal_model,
                "effort": "high",
                "batch_size": 15,
                "input_format": "stream-json",
                "output_format": "stream-json",
            }
        }
        bad_cfg.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ConfigValidationError) as exc:
            PromptGeneratorConfig.load(bad_cfg, base_dir=repo_root)
        assert "STRICT POLICY: Only 'gemini-3.1-pro-high' is permitted" in str(exc.value)


def test_reject_effort_downgrades(tmp_path):
    """Verify that attempting to downgrade effort raises ConfigValidationError."""
    repo_root = Path(__file__).parent.parent
    for illegal_effort in ["medium", "low", "default"]:
        bad_cfg = tmp_path / f"config_effort_{illegal_effort}.json"
        data = {
            "prompt_generator": {
                "provider": "antigravity_cli",
                "model": "gemini-3.1-pro-high",
                "effort": illegal_effort,
                "batch_size": 15,
                "input_format": "stream-json",
                "output_format": "stream-json",
            }
        }
        bad_cfg.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ConfigValidationError) as exc:
            PromptGeneratorConfig.load(bad_cfg, base_dir=repo_root)
        assert "STRICT POLICY: Only 'high' is permitted" in str(exc.value)


def test_reject_unlocked_batch_size(tmp_path):
    """Verify that non-15 batch size is rejected."""
    repo_root = Path(__file__).parent.parent
    for illegal_size in [10, 20, 25]:
        bad_cfg = tmp_path / f"config_batch_{illegal_size}.json"
        data = {
            "prompt_generator": {
                "provider": "antigravity_cli",
                "model": "gemini-3.1-pro-high",
                "effort": "high",
                "batch_size": illegal_size,
                "input_format": "stream-json",
                "output_format": "stream-json",
            }
        }
        bad_cfg.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ConfigValidationError) as exc:
            PromptGeneratorConfig.load(bad_cfg, base_dir=repo_root)
        assert "LOCKED POLICY: batch_size must be exactly 15" in str(exc.value)
