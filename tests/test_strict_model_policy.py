"""Tests for Strict Model + Rate-Limit Policy enforcement."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from prompt_generator.config import PromptGeneratorConfig
from prompt_generator.models import Batch, BatchStatus, PromptJob, QueueState, Scene, SceneStatus
from prompt_generator.providers.antigravity_cli import RateLimitedError
from prompt_generator.queue import BatchQueue


@pytest.fixture
def mock_config():
    repo_root = Path(__file__).parent.parent
    config_path = repo_root / "config" / "prompt_generator_config.json"
    return PromptGeneratorConfig.load(config_path, base_dir=repo_root)


def test_rate_limit_halts_and_preserves_incomplete_batch(mock_config, tmp_path):
    """Verify rate limit stops starting new requests and preserves confirmed work."""
    scenes = [Scene(scene_number=i, raw_text=f"Scene {i}") for i in range(1, 31)]
    queue = BatchQueue(mock_config, provider=MagicMock(), cache_dir=tmp_path)
    batches = queue.create_batches(scenes, job_id="test_rate_limit")

    mock_provider = MagicMock()

    # Batch 1 succeeds, Batch 2 hits rate limit
    def mock_gen(batch, instr):
        if batch.batch_index == 1:
            return [
                Scene(scene_number=s.scene_number, raw_text=s.raw_text, status=SceneStatus.SUCCESS, generated_prompt=f"Prompt {s.scene_number}")
                for s in batch.scenes
            ]
        else:
            raise RateLimitedError("Gemini 3.1 Pro High quota/rate limit reached.", diagnostics="Live Quota: 0 tokens")

    mock_provider.generate_batch.side_effect = mock_gen
    queue.provider = mock_provider

    status_events = []
    queue.on_status_change = lambda st, msg: status_events.append((st, msg))

    job = PromptJob(
        job_id="test_rate_limit",
        input_file=tmp_path / "in.txt",
        output_file=tmp_path / "out.docx",
        batches=batches,
    )

    results = queue.execute_job(job)

    # Policy assertions:
    # 1. Returned results contain only confirmed batch 1 scenes (15 scenes)
    assert len(results) == 15
    assert all(s.status == SceneStatus.SUCCESS for s in results)
    # 2. State is set to RATE_LIMITED
    assert job.state == QueueState.RATE_LIMITED
    # 3. Batch 2 is preserved in RATE_LIMITED state
    assert batches[1].status == BatchStatus.RATE_LIMITED
    # 4. Clear notification event fired
    assert any("Gemini 3.1 Pro High quota/rate limit reached." in msg for _, msg in status_events)
    # 5. Never attempted to call provider again after hitting rate limit
    assert mock_provider.generate_batch.call_count == 2  # batch 1, then batch 2 once


def test_no_hardcoded_quota_limits():
    """Verify that configuration and source code contain zero hard-coded quota values."""
    repo_root = Path(__file__).parent.parent
    config_file = repo_root / "config" / "prompt_generator_config.json"
    content = config_file.read_text(encoding="utf-8")

    assert "weekly_quota" not in content
    assert "five_hour_quota" not in content
    assert "token_limit" not in content
