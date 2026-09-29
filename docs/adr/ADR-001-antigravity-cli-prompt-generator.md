# ADR-001: Antigravity CLI Provider for Prompt Generator Subsystem

## Status
**Accepted**

## Context
The Prompt Generator requires streaming large, immutable prompt instructions (35,545 bytes) along with batches of scene text to generate high-precision image prompts using Google Gemini 3.1 Pro High.
Under Windows, passing this 35+ KB payload as a command-line argument (`agy -p "..."`) violates OS command length limits (8,191 chars for cmd, 32,767 for CreateProcess), causing process launch failures or silent truncation.
Furthermore, continuous streaming across multiple batches within a single CLI session causes prompt contamination, token inflation, and increased latency.

## Decisions

1. **Paired `stream-json` Stdin/Stdout**:
   - The engine uses `--input-format stream-json` paired with `--output-format stream-json` to pipe the verbatim 35+ KB instruction and scene payload cleanly via standard input.
2. **Explicit Response Timeout**:
   - The CLI is invoked with `--print-timeout 10m` to override the default 5-minute timeout and align with the application's 10-minute timeout for high reasoning effort.
3. **Isolated Process Per Batch**:
   - Each 15-scene batch spawns a fresh `agy` subprocess that terminates immediately upon batch completion. No conversational state is shared across batches.
4. **Deterministic JSON Schema**:
   - The engine passes `--json-schema config/scene_schema.json` and extracts `.result.structured_output.scenes`, eliminating fragile regex text parsing.
5. **Locked Model & Effort**:
   - Only `gemini-3.1-pro-high` with `high` reasoning effort is permitted. No silent fallbacks to Flash, 2.5 Pro, Claude, or GPT are permitted.
6. **Canonical Non-Contiguous Reconciliation**:
   - Output scenes are sorted strictly by canonical `scene_number` in ascending order without renumbering or assuming contiguous numbering.
7. **Standalone Quota Checks**:
   - Quota and usage checks execute as separate standalone headless commands (`agy -p /usage`), never within an active streaming session.

## Consequences
- **Positive**: Eliminates Windows argument length limits, prevents conversational context pollution, guarantees schema adherence, and ensures zero silent quality degradation.
- **Negative**: Spawning a fresh subprocess per batch adds minor initialization overhead, which is negligible compared to model reasoning time.
