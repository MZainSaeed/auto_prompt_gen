"""Antigravity CLI provider implementing paired stream-json and process isolation."""

import json
import logging
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from prompt_generator.config import PromptGeneratorConfig
from prompt_generator.models import Batch, Scene, SceneStatus
from prompt_generator.providers.base import PromptProvider

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Base error for provider operations."""
    pass


class CLINotFoundError(ProviderError):
    """Raised when agy executable is not found."""
    pass


class CLINotAuthenticatedError(ProviderError):
    """Raised when CLI session is not authenticated."""
    pass


class ModelUnavailableError(ProviderError):
    """Raised when gemini-3.1-pro-high is unavailable."""
    pass


class RateLimitedError(ProviderError):
    """Raised when provider reports rate limit or quota exhaustion."""
    def __init__(self, message: str, diagnostics: Optional[str] = None):
        super().__init__(message)
        self.diagnostics = diagnostics


class InvalidOutputError(ProviderError):
    """Raised when CLI response fails schema or JSON parsing."""
    pass


class AntigravityCLIProvider(PromptProvider):
    """Provider utilizing Google Antigravity CLI via paired stream-json."""

    def __init__(self, config: PromptGeneratorConfig):
        self.config = config
        found = shutil.which(config.executable)
        if not found:
            # Check default Windows and macOS installation directories
            candidates = [
                Path.home() / "AppData" / "Local" / "agy" / "bin" / "agy.exe",
                Path.home() / "AppData" / "Local" / "Programs" / "Antigravity" / "bin" / "agy.exe",
                Path.home() / "AppData" / "Local" / "Programs" / "Antigravity IDE" / "bin" / "agy.exe",
                Path.home() / ".gemini" / "antigravity-ide" / "bin" / "agy.exe",
                Path("C:/Program Files/Antigravity/bin/agy.exe"),
                Path("C:/Program Files/Antigravity IDE/bin/agy.exe"),
                Path.home() / ".local" / "bin" / "agy",
                Path.home() / ".gemini" / "antigravity-ide" / "bin" / "agy",
                Path("/usr/local/bin/agy"),
                Path("/opt/homebrew/bin/agy"),
                Path("/Applications/Antigravity.app/Contents/Resources/app/bin/agy"),
                Path("/Applications/Antigravity IDE.app/Contents/Resources/app/bin/agy"),
                Path.home() / "Applications" / "Antigravity.app" / "Contents" / "Resources" / "app" / "bin" / "agy",
                Path.home() / "Applications" / "Antigravity IDE.app" / "Contents" / "Resources" / "app" / "bin" / "agy",
            ]
            for cand in candidates:
                if cand.is_file():
                    found = str(cand)
                    break
        self._executable_path = found or config.executable

    def check_availability(self) -> bool:
        """Verify CLI existence and model availability."""
        if not shutil.which(self._executable_path) and not Path(self._executable_path).is_file():
            raise CLINotFoundError(
                f"CLI_NOT_FOUND: '{self.config.executable}' is not found in system PATH or default installation directories."
            )

        # Query available models via 'agy models'
        try:
            res = subprocess.run(
                [self._executable_path, "models"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if res.returncode != 0:
                if "auth" in res.stderr.lower() or "login" in res.stderr.lower():
                    raise CLINotAuthenticatedError(
                        f"CLI_NOT_AUTHENTICATED: {res.stderr.strip()}"
                    )
            # Check model presence
            if self.config.model not in res.stdout and self.config.model not in res.stderr:
                raise ModelUnavailableError(
                    f"MODEL_UNAVAILABLE: Model '{self.config.model}' not listed by provider. "
                    "Silent fallbacks are strictly prohibited."
                )
        except subprocess.TimeoutExpired:
            logger.warning("CLI models command timed out; assuming model availability.")
        except FileNotFoundError:
            raise CLINotFoundError(
                f"CLI_NOT_FOUND: '{self.config.executable}' executable could not be run."
            )

        return True

    def check_quota(self) -> str:
        """Execute standalone headless quota check: agy -p /usage.

        Never sends /usage inside an active stream-json session.
        """
        try:
            res = subprocess.run(
                [self._executable_path, "-p", "/usage"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return res.stdout.strip() or res.stderr.strip()
        except Exception as e:
            logger.error(f"Failed to query quota via standalone command: {e}")
            return f"QUOTA_CHECK_FAILED: {e}"

    def build_command(self) -> List[str]:
        """Construct the exact CLI command with mandatory paired flags and timeout.

        --dangerously-skip-permissions is required because the model reads AGENTS.md
        and attempts to verify the instruction.txt SHA-256 hash via run_command.
        Without this flag, the tool call is denied in headless mode and the model
        produces no output, causing INVALID_OUTPUT errors on every batch.
        """
        return [
            self._executable_path,
            "--model", self.config.model,
            "--effort", self.config.effort,
            "--input-format", self.config.input_format,
            "--output-format", self.config.output_format,
            "--print-timeout", self.config.print_timeout,
            "--json-schema", str(self.config.json_schema_file),
            "--dangerously-skip-permissions",
        ]

    def generate_batch(self, batch: Batch, instruction_text: str) -> List[Scene]:
        """Generate prompts for a batch in a fresh, isolated CLI process."""
        cmd = self.build_command()

        # Format batch scenes text
        scenes_payload = []
        for scene in batch.scenes:
            scenes_payload.append(
                f"--- SCENE {scene.scene_number} ---\n{scene.raw_text}"
            )
        full_scenes_text = "\n\n".join(scenes_payload)

        prompt_content = (
            f"{instruction_text}\n\n"
            f"============================================================\n"
            f"SCENES TO PROCESS IN THIS BATCH (Generate prompt for each):\n"
            f"============================================================\n\n"
            f"{full_scenes_text}"
        )

        input_event = json.dumps({
            "event": "user",
            "message": {
                "content": prompt_content
            }
        }) + "\n"

        logger.info(
            f"Spawning fresh isolated CLI process for Batch {batch.batch_id} "
            f"({len(batch.scenes)} scenes)..."
        )

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError:
            raise CLINotFoundError(
                f"CLI_NOT_FOUND: Failed to spawn '{self._executable_path}'."
            )

        stdout_data = ""
        stderr_data = ""
        timeout_seconds = self.config.timeout_minutes * 60

        try:
            stdout_data, stderr_data = proc.communicate(
                input=input_event, timeout=timeout_seconds
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise ProviderError(
                f"CLI response timed out after {self.config.timeout_minutes} minutes."
            )
        finally:
            if proc.poll() is None:
                proc.kill()

        # If process exited cleanly (returncode 0), attempt to extract structured scenes first
        structured_scenes: Optional[List[Dict[str, Any]]] = None
        if proc.returncode == 0:
            try:
                structured_scenes = self._extract_structured_scenes(
                    stdout_data, stderr_data=stderr_data, batch_id=batch.batch_id
                )
            except Exception:
                structured_scenes = None

        if structured_scenes is not None:
            return self._map_scenes_to_models(batch, structured_scenes)

        # Process failed or did not return structured output - check for errors
        error_text = stderr_data.lower()
        # Also inspect stream error events in stdout
        for line in stdout_data.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    ev = json.loads(line)
                    if "error" in ev or ev.get("type") == "error" or ev.get("status") == "error":
                        error_text += " " + json.dumps(ev).lower()
                except Exception:
                    pass

        # Check for genuine rate limit / quota exhaustion
        is_rate_limited = (
            "quota" in error_text
            or "rate limit" in error_text
            or "rate_limit" in error_text
            or "resource_exhausted" in error_text
            or bool(re.search(r"\b429\b", error_text))
        )
        if is_rate_limited:
            diagnostics = self.check_quota()
            raise RateLimitedError(
                "Gemini 3.1 Pro High quota/rate limit reached.",
                diagnostics=diagnostics,
            )

        if "model unavailable" in error_text or "model not found" in error_text:
            raise ModelUnavailableError(
                f"MODEL_UNAVAILABLE: Provider reported '{self.config.model}' is unavailable."
            )

        if proc.returncode != 0:
            if "auth" in error_text or "unauthorized" in error_text:
                raise CLINotAuthenticatedError(
                    f"CLI_NOT_AUTHENTICATED: Authentication failed: {stderr_data.strip()}"
                )
            raise ProviderError(
                f"CLI exited with non-zero code {proc.returncode}: {stderr_data.strip()}"
            )

        # Fallback to standard extraction to raise standard InvalidOutputError if returncode was 0
        structured_scenes = self._extract_structured_scenes(
            stdout_data, stderr_data=stderr_data, batch_id=batch.batch_id
        )
        return self._map_scenes_to_models(batch, structured_scenes)

    def _save_debug_output(self, batch_id: str, stdout_data: str, stderr_data: str) -> None:
        """Save raw CLI stdout/stderr to a debug file for post-mortem diagnosis."""
        try:
            debug_dir = Path(".prompt_gen_cache") / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_file = debug_dir / f"{batch_id}_{ts}.txt"
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(f"=== STDOUT ({len(stdout_data)} bytes) ===\n")
                f.write(stdout_data)
                f.write(f"\n\n=== STDERR ({len(stderr_data)} bytes) ===\n")
                f.write(stderr_data)
            logger.info(f"Raw CLI output saved to: {debug_file}")
        except Exception as e:
            logger.warning(f"Could not save debug output: {e}")

    def _extract_structured_scenes(
        self, stdout_data: str, stderr_data: str = "", batch_id: str = ""
    ) -> List[Dict[str, Any]]:
        """Parse NDJSON stream events and locate .result.structured_output.scenes.

        Extraction strategy (in priority order):
        1. result event → structured_output.scenes  (schema-validated path)
        2. result event → response/content text parsed as JSON → scenes key
        3. Accumulated text_delta chunks from ALL step_update events, joined and parsed
        4. Brute-force regex scan of entire stdout for a JSON block containing scenes

        Fallbacks 2-4 handle the common case where the model emits extra fields
        (e.g. toolAction, toolSummary) alongside scenes, which causes
        additionalProperties:false schema validation to fail and structured_output
        to be absent from the result event.
        """
        structured_scenes: Optional[List[Dict[str, Any]]] = None
        # Candidates from result.response / result.content text
        result_text_candidates: List[str] = []
        # ALL text_delta chunks accumulated in order to reconstruct full response
        accumulated_deltas: List[str] = []

        for line in stdout_data.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Normalize event type: real CLI uses "event" key; test mocks use "type" key
            event_type = event.get("event", "") or event.get("type", "")

            # --- Path 1: result.structured_output.scenes (primary, schema-validated) ---
            if event_type == "result" and "result" in event and isinstance(event["result"], dict):
                res_obj = event["result"]

                if "structured_output" in res_obj and isinstance(res_obj["structured_output"], dict):
                    so = res_obj["structured_output"]
                    if "scenes" in so and isinstance(so["scenes"], list):
                        structured_scenes = so["scenes"]
                        break  # highest-priority match; stop scanning

                # --- Path 2: result.response / result.content text as JSON ---
                for key in ("response", "content", "text", "message"):
                    response_text = res_obj.get(key, "") or ""
                    if isinstance(response_text, str) and response_text.strip():
                        result_text_candidates.insert(0, response_text.strip())
                        break

            # --- Accumulate text_delta chunks from step_update events ---
            elif event_type == "step_update":
                su = event.get("step_update", {}) or {}
                delta = (su.get("text_delta") or su.get("content") or "").strip()
                if delta:
                    accumulated_deltas.append(delta)

            # --- Path 4a: direct structured_output on event ---
            elif "structured_output" in event and isinstance(event["structured_output"], dict):
                so = event["structured_output"]
                if "scenes" in so and isinstance(so["scenes"], list):
                    structured_scenes = so["scenes"]

            # --- Path 4b: direct scenes key on event ---
            elif "scenes" in event and isinstance(event["scenes"], list):
                structured_scenes = event["scenes"]

        # If primary path succeeded, return immediately
        if structured_scenes is not None:
            return structured_scenes

        # --- Fallback A: try result text candidates (single high-quality text) ---
        for raw_text in result_text_candidates:
            candidate = self._try_parse_scenes_from_text(raw_text)
            if candidate is not None:
                logger.warning(
                    "structured_output missing from result event; recovered scenes from "
                    "result response text. This typically means schema validation failed "
                    "due to extra fields. Consider relaxing additionalProperties in scene_schema.json."
                )
                return candidate

        # --- Fallback B: join ALL accumulated text_delta chunks and parse as one JSON blob ---
        if accumulated_deltas:
            full_text = "".join(accumulated_deltas)
            candidate = self._try_parse_scenes_from_text(full_text)
            if candidate is not None:
                logger.warning(
                    "structured_output missing from result event; recovered scenes by "
                    "joining all text_delta chunks from step_update events."
                )
                return candidate

        # --- Fallback C: brute-force regex scan of entire stdout for any JSON with scenes ---
        candidate = self._brute_force_extract_scenes(stdout_data)
        if candidate is not None:
            logger.warning(
                "structured_output missing from result event; recovered scenes via "
                "brute-force regex scan of raw stdout."
            )
            return candidate

        # Save debug output so we can diagnose what the model actually returned
        self._save_debug_output(batch_id, stdout_data, stderr_data)

        raise InvalidOutputError(
            "INVALID_OUTPUT: Could not find '.result.structured_output.scenes' in stream output."
        )

    def _try_parse_scenes_from_text(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """Attempt to extract a valid scenes list from a raw text string.

        Tolerates extra top-level keys (e.g. toolAction, toolSummary) by only
        requiring that the parsed object contains a 'scenes' list where each
        item has integer 'scene_number' and non-empty string 'prompt'.
        """
        # Strip markdown code fences if present
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            # Remove opening fence (```json or ```) and closing fence
            inner = "\n".join(lines[1:-1]) if len(lines) > 2 else ""
            stripped = inner.strip()

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return None

        if not isinstance(parsed, dict):
            return None

        scenes = parsed.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            return None

        # Validate that every item has required fields with correct types
        validated: List[Dict[str, Any]] = []
        for item in scenes:
            if not isinstance(item, dict):
                return None
            scene_number = item.get("scene_number")
            prompt = item.get("prompt")
            if not isinstance(scene_number, int):
                return None
            if not isinstance(prompt, str) or not prompt.strip():
                return None
            validated.append({"scene_number": scene_number, "prompt": prompt})

        return validated if validated else None

    def _brute_force_extract_scenes(
        self, stdout_data: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Last-resort: scan raw stdout for any substring that looks like a scenes JSON blob.

        Handles cases where the CLI emits the JSON inside a larger text body or
        interleaved with non-JSON content.
        """
        # Look for JSON objects/arrays containing a "scenes" key
        # Strategy: find all positions of '"scenes"' and try to extract surrounding JSON
        for match in re.finditer(r'\{[^{}]*"scenes"\s*:', stdout_data, re.DOTALL):
            # Try expanding outward to find the full balanced JSON object
            start = match.start()
            depth = 0
            end = start
            for i, ch in enumerate(stdout_data[start:], start=start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > start:
                candidate_text = stdout_data[start:end]
                result = self._try_parse_scenes_from_text(candidate_text)
                if result is not None:
                    return result

        # Also try to find JSON code blocks in markdown-formatted output
        for code_match in re.finditer(r'```(?:json)?\s*\n(.*?)```', stdout_data, re.DOTALL):
            result = self._try_parse_scenes_from_text(code_match.group(1))
            if result is not None:
                return result

        return None

    def _map_scenes_to_models(
        self, batch: Batch, structured_scenes: List[Dict[str, Any]]
    ) -> List[Scene]:
        """Map structured JSON results back to Scene models."""
        returned_map = {}
        for item in structured_scenes:
            if "scene_number" in item and "prompt" in item:
                returned_map[int(item["scene_number"])] = str(item["prompt"])

        result_scenes: List[Scene] = []
        for s in batch.scenes:
            prompt = returned_map.get(s.scene_number)
            if not prompt or not prompt.strip():
                raise InvalidOutputError(
                    f"INVALID_OUTPUT: Missing prompt for Scene {s.scene_number} in batch response."
                )
            result_scenes.append(
                Scene(
                    scene_number=s.scene_number,
                    raw_text=s.raw_text,
                    status=SceneStatus.SUCCESS,
                    generated_prompt=prompt,
                )
            )

        return result_scenes
