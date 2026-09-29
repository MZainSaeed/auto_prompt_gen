"""Command-line entry point for the Prompt Generator Subsystem."""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure src directory is in sys.path when invoked directly
_src_dir = Path(__file__).resolve().parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

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


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def print_status(state: QueueState, message: str):
    print(f"[{state.value}] {message}")


def main():
    parser = argparse.ArgumentParser(
        description="Prompt Generator: High-fidelity image prompts using Antigravity CLI and Gemini 3.1 Pro High."
    )
    parser.add_argument(
        "-i", "--input", required=True, type=Path, help="Path to input script file (.txt, .docx)"
    )
    parser.add_argument(
        "-o", "--output", default=Path("generated_prompts.docx"), type=Path, help="Path to output DOCX file"
    )
    parser.add_argument(
        "-c", "--config", default=Path("config/prompt_generator_config.json"), type=Path, help="Path to configuration JSON"
    )
    parser.add_argument(
        "--job-id", default=None, type=str, help="Custom job ID (defaults to timestamp-based ID)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logging"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    repo_root = Path(__file__).parent.parent.parent
    config_path = args.config if args.config.is_absolute() else (repo_root / args.config)
    input_path = args.input if args.input.is_absolute() else (repo_root / args.input)
    output_path = args.output if args.output.is_absolute() else (repo_root / args.output)

    print("=" * 65)
    print("PROMPT GENERATOR — ANTIGRAVITY CLI")
    print("Model: gemini-3.1-pro-high | Effort: high | Batch Size: 15")
    print("=" * 65)

    # 1. Load configuration and verify canonical instruction hash
    try:
        cfg = PromptGeneratorConfig.load(config_path, base_dir=repo_root)
        print(f"[OK] Configuration loaded. Canonical instruction verified ({len(cfg.instruction_text)} bytes).")
    except InstructionIntegrityError as e:
        print(f"\n[FATAL] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Failed to load configuration: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Initialize provider and check availability
    provider = AntigravityCLIProvider(cfg)
    try:
        provider.check_availability()
        print(f"[OK] Antigravity CLI found and authenticated. Model '{cfg.model}' available.")
    except CLINotFoundError as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        print("Please ensure Antigravity CLI ('agy') is installed and in PATH.", file=sys.stderr)
        sys.exit(1)
    except CLINotAuthenticatedError as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        print("Please log in using Antigravity IDE or 'agy auth login'.", file=sys.stderr)
        sys.exit(1)
    except ModelUnavailableError as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[WARNING] Provider pre-check note: {e}")

    # 3. Parse input script
    try:
        scenes = parse_script_file(input_path)
        print(f"[OK] Parsed {len(scenes)} scenes from {input_path.name}.")
    except ParseError as e:
        print(f"\n[ERROR] Failed to parse script: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Could not read input file: {e}", file=sys.stderr)
        sys.exit(1)

    # 4. Create batches or restore from cache
    queue = BatchQueue(
        config=cfg,
        provider=provider,
        cache_dir=repo_root / ".prompt_gen_cache",
        on_status_change=print_status,
    )

    target_job_id = args.job_id
    if not target_job_id:
        # Check if an incomplete cached job exists for this input file
        target_job_id = queue.find_resumable_job(input_path)

    job = None
    if target_job_id:
        job = queue.restore_job_from_cache(target_job_id, output_file=output_path)
        if job:
            completed = job.completed_scenes
            total = job.total_scenes
            print(
                f"[RESUME] Found existing cached job '{target_job_id}' "
                f"({completed}/{total} scenes already confirmed)."
            )
            print("[RESUME] Skipping confirmed scenes. Resuming from incomplete batches.")

    if not job:
        job_id = target_job_id or f"job_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        batches = queue.create_batches(scenes, job_id=job_id)
        print(f"[OK] Partitioned into {len(batches)} locked batches (15 scenes per batch).")
        job = PromptJob(
            job_id=job_id,
            input_file=input_path,
            output_file=output_path,
            batches=batches,
        )

    try:
        print("\nStarting prompt generation...")
        reconciled = queue.execute_job(job)
        if job.state == QueueState.SUCCESS:
            print("\n" + "=" * 65)
            print("GENERATION COMPLETE")
            print(f"Total scenes: {len(reconciled)}")
            print(f"Output saved to: {output_path.resolve()}")
            print("=" * 65)
        elif job.state == QueueState.RATE_LIMITED:
            print("\n" + "!" * 65)
            print("RATE LIMITED — WORK PRESERVED")
            print("Gemini 3.1 Pro High quota/rate limit reached.")
            print(f"Completed scenes preserved in cache ({repo_root / '.prompt_gen_cache'}).")
            print("Run the same command again after quota recovery to resume seamlessly.")
            print("!" * 65)
            sys.exit(2)

    except Exception as e:
        print(f"\n[FAILED] Generation halted: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
