"""Tests for 15-scene batch chunking, process isolation, retry limits, and resume caching."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from prompt_generator.config import PromptGeneratorConfig
from prompt_generator.models import Batch, BatchStatus, PromptJob, QueueState, Scene, SceneStatus
from prompt_generator.queue import BatchQueue


@pytest.fixture
def mock_config():
    repo_root = Path(__file__).parent.parent
    config_path = repo_root / "config" / "prompt_generator_config.json"
    return PromptGeneratorConfig.load(config_path, base_dir=repo_root)


def test_493_scene_job_chunking(mock_config, tmp_path):
    """Verify 493 scenes partition into exactly 33 batches (32 of 15, 1 of 13)."""
    scenes = [Scene(scene_number=i, raw_text=f"Scene content {i}") for i in range(1, 494)]
    assert len(scenes) == 493

    queue = BatchQueue(mock_config, provider=MagicMock(), cache_dir=tmp_path)
    batches = queue.create_batches(scenes, job_id="test_493_job")

    assert len(batches) == 33
    for b in batches[:32]:
        assert len(b.scenes) == 15
    assert len(batches[32].scenes) == 13


def test_resume_skips_confirmed_scenes(mock_config, tmp_path):
    """Verify resume skips already completed batches and scenes."""
    scenes = [Scene(scene_number=i, raw_text=f"Scene {i}") for i in range(1, 31)]
    queue = BatchQueue(mock_config, provider=MagicMock(), cache_dir=tmp_path)
    batches = queue.create_batches(scenes, job_id="test_resume")

    # Mark batch 1 as complete
    batches[0].status = BatchStatus.SUCCESS
    for s in batches[0].scenes:
        s.status = SceneStatus.SUCCESS
        s.generated_prompt = f"Generated prompt for {s.scene_number}"

    mock_provider = MagicMock()
    # Batch 2 generator
    def mock_gen(batch, instr):
        return [
            Scene(scene_number=s.scene_number, raw_text=s.raw_text, status=SceneStatus.SUCCESS, generated_prompt=f"P {s.scene_number}")
            for s in batch.scenes
        ]
    mock_provider.generate_batch.side_effect = mock_gen

    queue.provider = mock_provider
    out_docx = tmp_path / "final.docx"
    job = PromptJob(job_id="test_resume", input_file=tmp_path / "in.txt", output_file=out_docx, batches=batches)

    reconciled = queue.execute_job(job)
    assert len(reconciled) == 30
    # Provider was called only ONCE (for batch 2), NOT for batch 1!
    assert mock_provider.generate_batch.call_count == 1
    assert out_docx.is_file()


def test_restore_from_cache_and_find_resumable_job(mock_config, tmp_path):
    """Verify cache serialization, auto-lookup, and restoration of partially completed jobs."""
    scenes = [Scene(scene_number=i, raw_text=f"Scene {i}") for i in range(1, 31)]
    queue = BatchQueue(mock_config, provider=MagicMock(), cache_dir=tmp_path)
    batches = queue.create_batches(scenes, job_id="job_persist_test")

    # Complete batch 1
    batches[0].status = BatchStatus.SUCCESS
    for s in batches[0].scenes:
        s.status = SceneStatus.SUCCESS
        s.generated_prompt = f"Prompt {s.scene_number}"

    # Batch 2 was rate-limited
    batches[1].status = BatchStatus.RATE_LIMITED
    batches[1].attempts = 2

    job = PromptJob(
        job_id="job_persist_test",
        input_file=tmp_path / "script.docx",
        output_file=tmp_path / "out.docx",
        batches=batches,
        state=QueueState.RATE_LIMITED,
    )
    queue.save_cache(job)

    # 1. Test find_resumable_job
    found_job_id = queue.find_resumable_job(tmp_path / "script.docx")
    assert found_job_id == "job_persist_test"

    # 2. Test restore_job_from_cache
    restored_job = queue.restore_job_from_cache("job_persist_test")
    assert restored_job is not None
    assert restored_job.completed_scenes == 15
    assert restored_job.batches[0].status == BatchStatus.SUCCESS
    assert restored_job.batches[0].is_complete() is True
    # Incomplete batch 2 should be reset to PENDING with 0 attempts for clean retry
    assert restored_job.batches[1].status == BatchStatus.PENDING
    assert restored_job.batches[1].attempts == 0
