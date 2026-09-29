# AGENTS.md — Operational Rules for AI Assistants

This repository (`auto_prompt_gen`) contains the permanent **Prompt Generator Subsystem**.
Before reading any code or making modifications, every AI coding assistant MUST read and strictly adhere to the operational directives documented here.

---

## 1. Mandatory Reading List

Before taking ANY action, future AI coding agents MUST inspect:
1. `AGENTS.md` (this file)
2. `docs/PROMPT_GENERATOR.md`
3. `docs/ANTIGRAVITY_CLI.md`
4. `docs/PROMPT_GENERATOR_ARCHITECTURE.md`
5. `docs/PROMPT_GENERATOR_CONFIGURATION.md`
6. `docs/PROMPT_GENERATOR_TROUBLESHOOTING.md`
7. `docs/adr/ADR-001-antigravity-cli-prompt-generator.md`

Do NOT rely on chat history. Do NOT rely on memory. The files above represent the permanent source of truth.

---

## 2. Canonical Instruction File Immutability

- **Path**: `instruction.txt` (in repository root)
- **Size**: 35,545 bytes (179 lines)
- **Authoritative SHA-256 Hash**:
  `1E8B4FE8F11C1B0625889855C765040E96761758735B32C4EC20E41301BDC007`

### Rules:
1. **STRICTLY IMMUTABLE**: Never edit, reformat, summarize, truncate, paraphrase, or prepend notices to `instruction.txt`.
2. **Hash Verification**: The generator MUST verify this SHA-256 hash before running any batch. If the hash differs by even a single byte, immediately halt with `INSTRUCTION_INTEGRITY_ERROR`. Never attempt automated repair.
3. **Verbatim Stdin Transmission**: The complete, verbatim 35+ KB instruction text must be streamed via `stdin` alongside each batch of scenes.

---

## 3. Strict Model & Rate-Limit Policy

The Prompt Generator may use **ONLY**:
- **Model**: `gemini-3.1-pro-high`
- **Effort**: `high`

**NO OTHER MODEL OR REASONING LEVEL IS ALLOWED.**

### Zero Fallbacks
Never silently switch to:
- Gemini 3.8/3.7/3.6 Flash
- Gemini 2.5 Pro
- Gemini 2.5 Flash
- Claude
- GPT
- Any other provider or lower reasoning effort

### Failure Classifications
- If `gemini-3.1-pro-high` is unavailable: halt immediately with `MODEL_UNAVAILABLE`.
- If provider reports rate limit / quota exhaustion: mark `RATE_LIMITED`.

### Required Behavior on Rate Limit / Quota Exhaustion
1. Immediately stop starting new generation requests.
2. Do not switch models.
3. Do not switch providers.
4. Do not silently reduce effort.
5. Preserve the current incomplete batch.
6. Display clear UI notification: `"Gemini 3.1 Pro High quota/rate limit reached."`.
7. Record provider diagnostics.
8. Check provider-supported usage/quota information using standalone headless command `agy -p /usage`.
9. Wait for legitimate quota/rate-limit recovery.
10. Resume the incomplete batch after recovery.
11. **Never regenerate already confirmed successful scenes.**

### Quota Classification & Live Ingestion
The system must distinguish:
- Temporary rate limit
- Five-hour quota exhaustion
- Weekly quota exhaustion
- Model unavailable
- Authentication failure

**Live Quota Information Rule**: Weekly, five-hour, and model quota values MUST NOT be hard-coded. Use provider-reported live quota data as authoritative.

### Anti-Evasion Policy
- **NO QUOTA-EVASION ACCOUNT ROTATION.**
- If multiple accounts are configured in a future supported phase, each must respect its own quota. Automatic rotation to bypass rate limits is strictly forbidden.

---

## 4. CLI Execution & Process Isolation Contract

### Command Invocation
Every generation batch must execute:
```powershell
agy --model gemini-3.1-pro-high --effort high --input-format stream-json --output-format stream-json --print-timeout 10m --json-schema config/scene_schema.json
```

### Critical Rules:
1. **Paired `stream-json`**: `--input-format stream-json` MUST always be paired with `--output-format stream-json`.
2. **Extended CLI Timeout**: `--print-timeout 10m` is required to override the Antigravity CLI default 5-minute timeout.
3. **Piped Stdin**: The full 35+ KB instruction and batch scenes are piped via `stdin`. Never pass large payloads as CLI arguments.
4. **Isolated Process Per Batch**:
   - Every 15-scene batch must spawn a **fresh, isolated `agy` subprocess** that is terminated immediately upon completion.
   - Do NOT send multiple batches through a single continuous process/conversation (to avoid token accumulation, cross-batch contamination, and latency degradation).
5. **Standalone Quota Checks**: Slash commands like `/usage` cannot run inside an active streaming session. Standalone headless invocation `agy -p /usage` is mandatory.
6. **Result Extraction**: Parse stream output events and extract scene data from:
   `.result.structured_output.scenes`

---

## 5. Batching & Ordering Contract

1. **Batch Size Locked**: `BATCH_SIZE = 15`. Exactly 15 scenes per CLI request. Locked and non-editable.
2. **Decoupling from Flow Batch Manager**: Flow Batch Manager uses 10 scenes per batch for image generation. Prompt Generator is a completely separate subsystem. Never mix batch sizes or code.
3. **Canonical Non-Contiguous Ordering**:
   - Verified scenes are sorted strictly by canonical `scene_number` in ascending numerical order.
   - **Never renumber scenes**.
   - **Never assume scene numbers are contiguous**. Gaps in input (e.g., scenes 1, 2, 4, 5) must be preserved without gap-filling.

---

## 6. Development Environment & Testing

- **Dedicated Virtual Environment**:
  `d:\Software\auto_prompt_gen\.venv\Scripts\python.exe`
- **Decoupled Environment**: Never invoke or depend on sibling project virtual environments (e.g. `Flow Batch Manager\.venv`).
- **Test Command**:
  ```powershell
  & "d:\Software\auto_prompt_gen\.venv\Scripts\python.exe" -m pytest tests/ -v
  ```
