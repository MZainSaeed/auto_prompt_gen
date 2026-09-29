# Prompt Generator (Antigravity CLI Subsystem)

A high-fidelity prompt generation engine built on Google Antigravity CLI and Gemini 3.1 Pro High reasoning.

## Overview
The Prompt Generator converts raw script files (TXT, DOCX) into production-ready image generation prompts adhering to canonical stylistic guidelines, absolute textless locks, and Roman/Modern subject locks.

This subsystem operates completely independently of downstream batch generation workflows (such as Flow Batch Manager).

## Key Characteristics
- **Exclusive Model & Effort**: Runs exclusively on `gemini-3.1-pro-high` at `high` reasoning effort. No silent model switching, fallbacks, or effort degradation.
- **Canonical Instruction Hash Lock**: Validates `instruction.txt` SHA-256 (`1E8B4FE8F11C1B0625889855C765040E96761758735B32C4EC20E41301BDC007`) before execution.
- **Paired Stream Stdin/Stdout**: Streams the 35+ KB instruction and batch payloads over `stdin` using paired flags `--input-format stream-json --output-format stream-json --print-timeout 10m --json-schema config/scene_schema.json`.
- **Process Isolation**: Each 15-scene batch is executed in a dedicated, clean Antigravity CLI process. No conversational state is shared across batches.
- **Locked Batch Size**: Exactly 15 scenes per batch (`BATCH_SIZE = 15`).
- **Deterministic Reconciliation**: Parses `.result.structured_output.scenes` using JSON Schema, checks completeness, and deterministically sorts prompts by canonical `scene_number` without renumbering or assuming contiguous numbers.
- **DOCX Production**: Automatically exports verified prompts to structured DOCX files.

## Documentation Index
- [AGENTS.md](AGENTS.md): Strict operational rules for AI assistants.
- [docs/PROMPT_GENERATOR.md](docs/PROMPT_GENERATOR.md): Complete subsystem manual.
- [docs/ANTIGRAVITY_CLI.md](docs/ANTIGRAVITY_CLI.md): Antigravity CLI provider specification.
- [docs/PROMPT_GENERATOR_ARCHITECTURE.md](docs/PROMPT_GENERATOR_ARCHITECTURE.md): System architecture and data flow.
- [docs/PROMPT_GENERATOR_CONFIGURATION.md](docs/PROMPT_GENERATOR_CONFIGURATION.md): Configuration reference.
- [docs/PROMPT_GENERATOR_TROUBLESHOOTING.md](docs/PROMPT_GENERATOR_TROUBLESHOOTING.md): Error codes and recovery procedures.
- [docs/adr/ADR-001-antigravity-cli-prompt-generator.md](docs/adr/ADR-001-antigravity-cli-prompt-generator.md): Architecture Decision Record.

## Development & Testing
```powershell
# Activate dedicated virtual environment
& ".\.venv\Scripts\Activate.ps1"

# Run full test suite
& ".\.venv\Scripts\python.exe" -m pytest tests/ -v
```
