"""Queue, 15-scene batching engine, and resume management."""

import json
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional

from prompt_generator.config import LOCKED_BATCH_SIZE, PromptGeneratorConfig
from prompt_generator.docx_exporter import export_prompts_to_docx
from prompt_generator.models import (
    Batch,
    BatchStatus,
    PromptJob,
    QueueState,
    Scene,
    SceneStatus,
)
from prompt_generator.providers.antigravity_cli import RateLimitedError
from prompt_generator.providers.base import PromptProvider
from prompt_generator.reconciliation import reconcile_scenes

logger = logging.getLogger(__name__)


class BatchQueue:
    """Orchestrates 15-scene batches, execution lifecycle, retries, and persistence."""

    def __init__(
        self,
        config: PromptGeneratorConfig,
        provider: PromptProvider,
        cache_dir: Optional[Path] = None,
        on_status_change: Optional[Callable[[QueueState, str], None]] = None,
    ):
        self.config = config
        self.provider = provider
        self.batch_size = LOCKED_BATCH_SIZE
        self.cache_dir = cache_dir or Path(".prompt_gen_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.on_status_change = on_status_change

    def _notify(self, state: QueueState, message: str) -> None:
        if self.on_status_change:
            self.on_status_change(state, message)

    def create_batches(self, scenes: List[Scene], job_id: str) -> List[Batch]:
        """Partition scenes into strict locked batches of 15."""
        batches: List[Batch] = []
        total = len(scenes)

        for i in range(0, total, self.batch_size):
            chunk = scenes[i : i + self.batch_size]
            batch_idx = (i // self.batch_size) + 1
            batch_id = f"{job_id}_batch_{batch_idx:03d}"
            batches.append(
                Batch(
                    batch_id=batch_id,
                    batch_index=batch_idx,
                    scenes=chunk,
                    status=BatchStatus.PENDING,
                )
            )
        return batches

    def save_cache(self, job: PromptJob) -> None:
        """Persist job state to cache directory for seamless resume."""
        cache_file = self.cache_dir / f"{job.job_id}.json"
        data = {
            "job_id": job.job_id,
            "input_file": str(job.input_file),
            "output_file": str(job.output_file),
            "state": job.state.value,
            "batches": [
                {
                    "batch_id": b.batch_id,
                    "batch_index": b.batch_index,
                    "status": b.status.value,
                    "attempts": b.attempts,
                    "error": b.error,
                    "scenes": [s.to_dict() for s in b.scenes],
                }
                for b in job.batches
            ],
        }
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_cache(self, job_id: str) -> Optional[Dict]:
        """Load job state from cache if available."""
        cache_file = self.cache_dir / f"{job_id}.json"
        if cache_file.is_file():
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def find_resumable_job(self, input_file: Path) -> Optional[str]:
        """Find the latest incomplete job for the given input file in the cache directory."""
        if not self.cache_dir.is_dir():
            return None

        candidates = []
        input_name = input_file.name
        input_abs = str(input_file.resolve())

        for cache_file in self.cache_dir.glob("job_*.json"):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cached_input = data.get("input_file", "")
                if cached_input == input_abs or Path(cached_input).name == input_name:
                    state = data.get("state", "")
                    if state != QueueState.SUCCESS.value:
                        mtime = cache_file.stat().st_mtime
                        candidates.append((mtime, data.get("job_id", cache_file.stem)))
            except Exception:
                continue

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]
        return None

    def restore_job_from_cache(
        self, job_id: str, output_file: Optional[Path] = None
    ) -> Optional[PromptJob]:
        """Restore an existing job from cache, preserving completed batches and scenes."""
        data = self.load_cache(job_id)
        if not data:
            return None

        batches: List[Batch] = []
        for b_data in data.get("batches", []):
            batch = Batch.from_dict(b_data)
            if batch.status in (
                BatchStatus.RATE_LIMITED,
                BatchStatus.RUNNING,
                BatchStatus.FAILED,
            ):
                batch.status = BatchStatus.PENDING
                batch.attempts = 0
                batch.error = None
            batches.append(batch)

        out_path = (
            output_file
            if output_file is not None
            else Path(data.get("output_file", "generated_prompts.docx"))
        )
        return PromptJob(
            job_id=job_id,
            input_file=Path(data["input_file"]),
            output_file=out_path,
            batches=batches,
            state=QueueState(data.get("state", QueueState.QUEUED.value)),
        )

    def execute_job(self, job: PromptJob) -> List[Scene]:
        """Execute all batches in the job sequentially using isolated processes.

        Preserves confirmed scenes and respects the Strict Model & Rate-Limit Policy.
        """
        job.state = QueueState.RUNNING
        self._notify(QueueState.RUNNING, f"Starting Prompt Generator Job {job.job_id}")

        all_completed_scenes: Dict[int, Scene] = {}

        # Collect already completed scenes from cache / prior runs
        for batch in job.batches:
            if batch.is_complete():
                for s in batch.scenes:
                    all_completed_scenes[s.scene_number] = s

        for batch in job.batches:
            if batch.is_complete():
                logger.info(f"Skipping already completed Batch {batch.batch_id}")
                continue

            batch.status = BatchStatus.RUNNING
            success = False

            while batch.attempts < self.config.max_retries and not success:
                batch.attempts += 1
                try:
                    self._notify(
                        QueueState.RUNNING,
                        f"Running Batch {batch.batch_index}/{len(job.batches)} "
                        f"(Attempt {batch.attempts}/{self.config.max_retries})",
                    )
                    # Isolated process per batch
                    result_scenes = self.provider.generate_batch(
                        batch, self.config.instruction_text
                    )
                    batch.scenes = result_scenes
                    batch.status = BatchStatus.SUCCESS
                    success = True

                    for s in result_scenes:
                        all_completed_scenes[s.scene_number] = s

                    self.save_cache(job)

                except RateLimitedError as rle:
                    batch.status = BatchStatus.RATE_LIMITED
                    job.state = QueueState.RATE_LIMITED
                    self.save_cache(job)
                    msg = "Gemini 3.1 Pro High quota/rate limit reached."
                    self._notify(QueueState.RATE_LIMITED, msg)
                    logger.error(f"{msg} Diagnostics: {rle.diagnostics}")
                    # Policy: Immediately stop starting new requests, preserve incomplete batch
                    return list(all_completed_scenes.values())

                except Exception as e:
                    logger.warning(
                        f"Batch {batch.batch_id} attempt {batch.attempts} failed: {e}"
                    )
                    batch.error = str(e)
                    if batch.attempts >= self.config.max_retries:
                        batch.status = BatchStatus.FAILED
                        job.state = QueueState.FAILED
                        self.save_cache(job)
                        self._notify(
                            QueueState.FAILED,
                            f"Batch {batch.batch_id} exceeded max retries: {e}",
                        )
                        raise

            if not success:
                job.state = QueueState.FAILED
                self.save_cache(job)
                raise RuntimeError(f"Batch {batch.batch_id} failed to complete.")

        # Full job reconciliation
        all_expected_scenes: List[Scene] = [s for b in job.batches for s in b.scenes]
        reconciled = reconcile_scenes(
            all_expected_scenes, list(all_completed_scenes.values())
        )

        # Export to DOCX
        export_prompts_to_docx(reconciled, job.output_file)

        job.state = QueueState.SUCCESS
        self.save_cache(job)
        self._notify(
            QueueState.SUCCESS,
            f"Successfully generated and reconciled {len(reconciled)} scenes into {job.output_file}",
        )
        return reconciled
