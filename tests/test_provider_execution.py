"""Tests for AntigravityCLIProvider execution, streaming JSON parsing, and error classification."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from prompt_generator.config import PromptGeneratorConfig
from prompt_generator.models import Batch, Scene, SceneStatus
from prompt_generator.providers.antigravity_cli import (
    AntigravityCLIProvider,
    CLINotAuthenticatedError,
    InvalidOutputError,
    ModelUnavailableError,
    RateLimitedError,
)


@pytest.fixture
def mock_config():
    repo_root = Path(__file__).parent.parent
    config_path = repo_root / "config" / "prompt_generator_config.json"
    return PromptGeneratorConfig.load(config_path, base_dir=repo_root)


def test_structured_output_stream_parsing(mock_config):
    """Verify provider parses .result.structured_output.scenes from stream events."""
    provider = AntigravityCLIProvider(mock_config)
    batch = Batch(
        batch_id="batch_001",
        batch_index=1,
        scenes=[
            Scene(scene_number=1, raw_text="Castle scene"),
            Scene(scene_number=2, raw_text="Forest scene"),
        ],
    )

    mock_event_1 = json.dumps({"type": "status", "message": "processing"})
    mock_event_2 = json.dumps({
        "type": "result",
        "result": {
            "structured_output": {
                "scenes": [
                    {"scene_number": 1, "prompt": "Prompt for scene 1"},
                    {"scene_number": 2, "prompt": "Prompt for scene 2"},
                ]
            }
        },
    })
    stdout_stream = f"{mock_event_1}\n{mock_event_2}\n"

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (stdout_stream, "")
        mock_proc.returncode = 0
        mock_proc.poll.return_value = 0
        mock_popen.return_value = mock_proc

        scenes = provider.generate_batch(batch, mock_config.instruction_text)
        assert len(scenes) == 2
        assert scenes[0].scene_number == 1
        assert scenes[0].generated_prompt == "Prompt for scene 1"
        assert scenes[1].scene_number == 2
        assert scenes[1].generated_prompt == "Prompt for scene 2"


def test_fallback_recovery_from_response_text_with_extra_fields(mock_config):
    """Verify provider recovers scenes from result.response when structured_output is absent.

    Regression test for the case where the model emits extra top-level fields
    (toolAction, toolSummary) alongside 'scenes', causing additionalProperties:false
    schema validation to fail and structured_output to be absent from the result event.
    The provider must fall back to parsing result.response as JSON.
    """
    provider = AntigravityCLIProvider(mock_config)
    batch = Batch(
        batch_id="batch_001",
        batch_index=1,
        scenes=[
            Scene(scene_number=1, raw_text="Castle scene"),
            Scene(scene_number=2, raw_text="Forest scene"),
        ],
    )

    # Simulate CLI result event WITHOUT structured_output (schema validation failed)
    # but WITH the raw response text that contains scenes + extra fields
    response_text_with_extras = json.dumps({
        "scenes": [
            {"scene_number": 1, "prompt": "Prompt for scene 1"},
            {"scene_number": 2, "prompt": "Prompt for scene 2"},
        ],
        "toolAction": "Finishing task",   # extra field that breaks additionalProperties:false
        "toolSummary": "Finish task",     # extra field that breaks additionalProperties:false
    })
    result_event = json.dumps({
        "event": "result",
        "result": {
            "status": "SUCCESS",
            "response": response_text_with_extras,
            # Note: structured_output is intentionally absent (schema validation failed)
        },
    })
    stdout_stream = f"{result_event}\n"

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (stdout_stream, "")
        mock_proc.returncode = 0
        mock_proc.poll.return_value = 0
        mock_popen.return_value = mock_proc

        scenes = provider.generate_batch(batch, mock_config.instruction_text)
        assert len(scenes) == 2
        assert scenes[0].scene_number == 1
        assert scenes[0].generated_prompt == "Prompt for scene 1"
        assert scenes[1].scene_number == 2
        assert scenes[1].generated_prompt == "Prompt for scene 2"


def test_fallback_recovery_from_step_update_text_delta(mock_config):
    """Verify provider recovers scenes from step_update.text_delta when result event has no structured_output."""
    provider = AntigravityCLIProvider(mock_config)
    batch = Batch(
        batch_id="batch_001",
        batch_index=1,
        scenes=[Scene(scene_number=5, raw_text="Battle scene")],
    )

    delta_text = json.dumps({
        "scenes": [{"scene_number": 5, "prompt": "Epic battle prompt"}],
        "toolAction": "Finishing task",
        "toolSummary": "Finish",
    })
    step_update_event = json.dumps({
        "event": "step_update",
        "step_update": {
            "step_type": "agent_response",
            "text_delta": delta_text,
        },
    })
    result_event = json.dumps({
        "event": "result",
        "result": {"status": "SUCCESS", "response": ""},
    })
    stdout_stream = f"{step_update_event}\n{result_event}\n"

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (stdout_stream, "")
        mock_proc.returncode = 0
        mock_proc.poll.return_value = 0
        mock_popen.return_value = mock_proc

        scenes = provider.generate_batch(batch, mock_config.instruction_text)
        assert len(scenes) == 1
        assert scenes[0].scene_number == 5
        assert scenes[0].generated_prompt == "Epic battle prompt"


def test_rate_limited_detection(mock_config):
    """Verify provider detects rate limit / quota exhaustion and halts."""
    provider = AntigravityCLIProvider(mock_config)
    batch = Batch(
        batch_id="batch_001",
        batch_index=1,
        scenes=[Scene(scene_number=1, raw_text="Scene text")],
    )

    with patch("subprocess.Popen") as mock_popen, patch.object(provider, "check_quota", return_value="Quota: 0 remaining"):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("", "Error 429: Resource exhausted: quota exceeded")
        mock_proc.returncode = 1
        mock_proc.poll.return_value = 1
        mock_popen.return_value = mock_proc

        with pytest.raises(RateLimitedError) as exc:
            provider.generate_batch(batch, mock_config.instruction_text)

        assert "Gemini 3.1 Pro High quota/rate limit reached." in str(exc.value)
        assert exc.value.diagnostics == "Quota: 0 remaining"


def test_model_unavailable_detection(mock_config):
    """Verify provider halts with ModelUnavailableError when model is missing."""
    provider = AntigravityCLIProvider(mock_config)
    batch = Batch(
        batch_id="batch_001",
        batch_index=1,
        scenes=[Scene(scene_number=1, raw_text="Scene text")],
    )

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("", "Model unavailable: gemini-3.1-pro-high not found")
        mock_proc.returncode = 1
        mock_proc.poll.return_value = 1
        mock_popen.return_value = mock_proc

        with pytest.raises(ModelUnavailableError):
            provider.generate_batch(batch, mock_config.instruction_text)


def test_standalone_usage_check(mock_config):
    """Verify check_quota calls standalone command 'agy -p /usage'."""
    provider = AntigravityCLIProvider(mock_config)

    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.stdout = "Weekly Quota: 85% remaining"
        mock_res.stderr = ""
        mock_res.returncode = 0
        mock_run.return_value = mock_res

        output = provider.check_quota()
        assert "Weekly Quota: 85% remaining" in output

        call_args = mock_run.call_args[0][0]
        assert "-p" in call_args
        assert "/usage" in call_args


def test_scene_429_not_falsely_detected_as_rate_limit(mock_config):
    """Verify that a batch containing Scene 429 is not falsely detected as HTTP 429 rate limit."""
    provider = AntigravityCLIProvider(mock_config)
    batch = Batch(
        batch_id="batch_029",
        batch_index=29,
        scenes=[Scene(scene_number=429, raw_text="Scene 429 text")],
    )

    mock_event = json.dumps({
        "type": "result",
        "result": {
            "structured_output": {
                "scenes": [
                    {"scene_number": 429, "prompt": "Prompt for scene 429"}
                ]
            }
        },
    })

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (f"{mock_event}\n", "")
        mock_proc.returncode = 0
        mock_proc.poll.return_value = 0
        mock_popen.return_value = mock_proc

        scenes = provider.generate_batch(batch, mock_config.instruction_text)
        assert len(scenes) == 1
        assert scenes[0].scene_number == 429
        assert scenes[0].generated_prompt == "Prompt for scene 429"
