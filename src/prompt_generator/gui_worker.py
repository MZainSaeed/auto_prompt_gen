"""Background worker thread for Prompt Generator GUI.

Runs the full generation pipeline in a daemon thread and posts
status events to a thread-safe queue for the UI to consume.
"""

import logging
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    LOG = "log"
    PROGRESS = "progress"
    STATUS = "status"
    QUOTA = "quota"
    DONE = "done"
    ERROR = "error"


class LogLevel(str, Enum):
    INFO = "info"
    OK = "ok"
    WARN = "warn"
    ERROR = "error"
    RESUME = "resume"


@dataclass
class WorkerEvent:
    type: EventType
    payload: Any = None


@dataclass
class ProgressPayload:
    batch_index: int
    total_batches: int
    scenes_done: int
    total_scenes: int
    message: str = ""


@dataclass
class LogPayload:
    level: LogLevel
    message: str
    timestamp: str = field(
        default_factory=lambda: datetime.now().strftime("%H:%M:%S")
    )


class GenerationWorker:
    """Runs the prompt generation pipeline in a background thread.

    Posts WorkerEvent objects to self.event_queue which the GUI
    should poll via root.after().
    """

    def __init__(self, input_file: Path, output_file: Path, repo_root: Path):
        self.input_file = input_file
        self.output_file = output_file
        self.repo_root = repo_root
        self.event_queue: queue.Queue[WorkerEvent] = queue.Queue()
        self._cancel_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

    # ------------------------------------------------------------------ #
    #  Control API                                                         #
    # ------------------------------------------------------------------ #

    def start(self):
        """Start the generation in a background daemon thread."""
        if self._is_running:
            return
        self._cancel_flag.clear()
        self._is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self):
        """Request cancellation. Current batch will finish before stopping."""
        self._cancel_flag.set()

    @property
    def is_running(self) -> bool:
        return self._is_running

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _post(self, event: WorkerEvent):
        self.event_queue.put_nowait(event)

    def _log(self, level: LogLevel, message: str):
        self._post(WorkerEvent(
            type=EventType.LOG,
            payload=LogPayload(level=level, message=message),
        ))

    def _progress(self, batch_index: int, total_batches: int,
                  scenes_done: int, total_scenes: int, message: str = ""):
        self._post(WorkerEvent(
            type=EventType.PROGRESS,
            payload=ProgressPayload(
                batch_index=batch_index,
                total_batches=total_batches,
                scenes_done=scenes_done,
                total_scenes=total_scenes,
                message=message,
            ),
        ))

    # ------------------------------------------------------------------ #
    #  Main run                                                            #
    # ------------------------------------------------------------------ #

    def _run(self):
        """Full pipeline executed inside the background thread."""
        import sys

        # Ensure src is on path
        src_dir = self.repo_root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))

        try:
            from prompt_generator.config import PromptGeneratorConfig
            from prompt_generator.integrity import InstructionIntegrityError
            from prompt_generator.models import PromptJob, QueueState
            from prompt_generator.parser import ParseError, parse_script_file
            from prompt_generator.providers.antigravity_cli import (
                AntigravityCLIProvider,
                CLINotAuthenticatedError,
                CLINotFoundError,
                ModelUnavailableError,
                RateLimitedError,
            )
            from prompt_generator.queue import BatchQueue

            config_path = self.repo_root / "config" / "prompt_generator_config.json"

            # Step 1: Load config
            try:
                cfg = PromptGeneratorConfig.load(config_path, base_dir=self.repo_root)
                self._log(LogLevel.OK, f"Configuration loaded. Canonical instruction verified ({len(cfg.instruction_text)} bytes).")
            except InstructionIntegrityError as e:
                self._log(LogLevel.ERROR, f"INSTRUCTION_INTEGRITY_ERROR: {e}")
                self._post(WorkerEvent(type=EventType.ERROR, payload=str(e)))
                return
            except Exception as e:
                self._log(LogLevel.ERROR, f"Failed to load configuration: {e}")
                self._post(WorkerEvent(type=EventType.ERROR, payload=str(e)))
                return

            # Step 2: Check provider
            provider = AntigravityCLIProvider(cfg)
            try:
                provider.check_availability()
                self._log(LogLevel.OK, f"CLI authenticated. Model '{cfg.model}' available.")
            except CLINotFoundError as e:
                self._log(LogLevel.ERROR, f"CLI not found: {e}")
                self._post(WorkerEvent(type=EventType.ERROR, payload=str(e)))
                return
            except CLINotAuthenticatedError as e:
                self._log(LogLevel.ERROR, f"Not authenticated: {e}")
                self._post(WorkerEvent(type=EventType.ERROR, payload=str(e)))
                return
            except ModelUnavailableError as e:
                self._log(LogLevel.ERROR, f"MODEL_UNAVAILABLE: {e}")
                self._post(WorkerEvent(type=EventType.ERROR, payload=str(e)))
                return
            except Exception as e:
                self._log(LogLevel.WARN, f"Provider check note: {e}")

            if self._cancel_flag.is_set():
                self._log(LogLevel.WARN, "Cancelled before generation started.")
                self._post(WorkerEvent(type=EventType.STATUS, payload="cancelled"))
                return

            # Step 3: Parse scenes
            try:
                scenes = parse_script_file(self.input_file)
                self._log(LogLevel.OK, f"Parsed {len(scenes)} scenes from {self.input_file.name}.")
            except ParseError as e:
                self._log(LogLevel.ERROR, f"Failed to parse script: {e}")
                self._post(WorkerEvent(type=EventType.ERROR, payload=str(e)))
                return
            except Exception as e:
                self._log(LogLevel.ERROR, f"Could not read input file: {e}")
                self._post(WorkerEvent(type=EventType.ERROR, payload=str(e)))
                return

            # Step 4: Create queue + job
            cache_dir = Path.cwd() / ".prompt_gen_cache"

            # Status callback for queue → posts to event queue
            def on_status(state, message):
                level_map = {
                    QueueState.RUNNING: LogLevel.INFO,
                    QueueState.SUCCESS: LogLevel.OK,
                    QueueState.FAILED: LogLevel.ERROR,
                    QueueState.RATE_LIMITED: LogLevel.WARN,
                }
                level = level_map.get(state, LogLevel.INFO)
                self._log(level, message)

                # Parse progress from message like "Running Batch 5/26 (Attempt 1/3)"
                import re
                m = re.search(r"Running Batch (\d+)/(\d+)", message)
                if m:
                    bi, bt = int(m.group(1)), int(m.group(2))
                    scenes_done = (bi - 1) * cfg.batch_size
                    total = len(scenes)
                    self._progress(bi, bt, min(scenes_done, total), total, message)

                # Also check for "Skipping already completed"
                ms = re.search(r"Skipping already completed Batch .*batch_(\d+)", message)
                if ms:
                    bi = int(ms.group(1))
                    scenes_done = bi * cfg.batch_size
                    # We'll estimate total_batches from scenes
                    total_batches = (len(scenes) + cfg.batch_size - 1) // cfg.batch_size
                    self._progress(bi, total_batches, min(scenes_done, len(scenes)), len(scenes))

                self._post(WorkerEvent(type=EventType.STATUS, payload=state.value))

                # Respect cancel flag between batches
                if self._cancel_flag.is_set():
                    raise KeyboardInterrupt("User cancelled")

            bqueue = BatchQueue(
                config=cfg,
                provider=provider,
                cache_dir=cache_dir,
                on_status_change=on_status,
            )

            target_job_id = bqueue.find_resumable_job(self.input_file)
            job = None

            if target_job_id:
                job = bqueue.restore_job_from_cache(target_job_id, output_file=self.output_file)
                if job:
                    completed = job.completed_scenes
                    total = job.total_scenes
                    self._log(LogLevel.RESUME, f"Found cached job '{target_job_id}' ({completed}/{total} scenes confirmed). Resuming...")
                    self._progress(0, (total + cfg.batch_size - 1) // cfg.batch_size, completed, total, "Resuming...")

            if not job:
                job_id = f"job_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
                batches = bqueue.create_batches(scenes, job_id=job_id)
                total_batches = len(batches)
                self._log(LogLevel.OK, f"Partitioned into {total_batches} locked batches (15 scenes per batch).")
                self._progress(0, total_batches, 0, len(scenes))
                job = PromptJob(
                    job_id=job_id,
                    input_file=self.input_file,
                    output_file=self.output_file,
                    batches=batches,
                )

            # Step 5: Execute
            self._log(LogLevel.INFO, "Starting prompt generation...")
            try:
                reconciled = bqueue.execute_job(job)

                if job.state == QueueState.SUCCESS:
                    total_scenes = len(reconciled)
                    self._log(LogLevel.OK, f"✓ Generation complete! {total_scenes} scenes written to {self.output_file.name}")
                    self._progress(
                        job.total_scenes // cfg.batch_size,
                        job.total_scenes // cfg.batch_size,
                        total_scenes,
                        total_scenes,
                        "Complete",
                    )
                    self._post(WorkerEvent(type=EventType.DONE, payload=str(self.output_file)))

                elif job.state == QueueState.RATE_LIMITED:
                    self._log(LogLevel.WARN, "Rate limited — work preserved in cache. Restart to resume after quota recovery.")
                    self._post(WorkerEvent(type=EventType.STATUS, payload="rate_limited"))

            except KeyboardInterrupt:
                self._log(LogLevel.WARN, "Generation cancelled by user. Progress saved in cache.")
                self._post(WorkerEvent(type=EventType.STATUS, payload="cancelled"))

            except Exception as e:
                self._log(LogLevel.ERROR, f"Generation halted: {e}")
                self._post(WorkerEvent(type=EventType.ERROR, payload=str(e)))

        except Exception as e:
            self._log(LogLevel.ERROR, f"Unexpected error: {e}")
            self._post(WorkerEvent(type=EventType.ERROR, payload=str(e)))
        finally:
            self._is_running = False
