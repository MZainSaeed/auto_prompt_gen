# Prompt Generator Subsystem Specification

## 1. Purpose & Scope
The Prompt Generator Subsystem transforms raw film, video, or episodic script texts into high-precision, stylistic image-generation prompts. It is an independent subsystem hosted within `auto_prompt_gen`.

It is **completely distinct** from downstream execution engines such as the Flow Batch Manager:
- **Prompt Generator**: Produces text prompts in locked batches of 15 scenes using Antigravity CLI and Gemini 3.1 Pro High.
- **Flow Batch Manager**: Consumes generated prompts in downstream image-generation workflows with batches of 10 scenes.

---

## 2. Pipeline Lifecycle

```
[Raw Script: TXT / DOCX]
          │
          ▼
   [Scene Parser] ──────────► Checks for duplicate scenes, parses Scene N: blocks
          │
          ▼
  [15-Scene Batches] ───────► Chunking into locked batches of 15 (BATCH_SIZE = 15)
          │
          ▼
[Isolated CLI Subprocess] ──► Spawns fresh agy process per batch
          │                   Pipes instruction.txt (35KB) + 15 scenes via stdin
          │                   Uses --input-format stream-json --output-format stream-json
          │                   Uses --print-timeout 10m --json-schema config/scene_schema.json
          ▼
 [Structured Output] ───────► Parses .result.structured_output.scenes
          │
          ▼
   [Reconciliation] ────────► Verifies all scenes returned, sorts by canonical scene_number
          │                   Preserves non-contiguous sequences without renumbering
          ▼
   [DOCX Exporter] ─────────► Produces final structured DOCX document
```

---

## 3. Strict Model & Rate-Limit Policy

The Prompt Generator operates under a strict, non-negotiable model policy:
- **Model**: `gemini-3.1-pro-high`
- **Reasoning Effort**: `high`
- **Zero Fallbacks**: Never switch silently to Gemini Flash (3.8/3.7/3.6/2.5), Gemini 2.5 Pro, Claude, GPT, or lower reasoning effort.
- **Failure Handling**:
  - `MODEL_UNAVAILABLE`: Immediate halt if model is missing.
  - `RATE_LIMITED`: On rate limit or quota exhaustion, immediately cease dispatching new requests, preserve the incomplete batch, notify the user (`"Gemini 3.1 Pro High quota/rate limit reached."`), record provider diagnostics, wait for legitimate quota recovery, and resume without regenerating confirmed scenes.
- **Quota Tracking**: Never hardcode quota limits; parse live provider feedback.
- **Zero Quota-Evasion Rotation**: Do not use account switching to bypass limits.

---

## 4. Input Parser Specification

- **Formats**: Plain text (`.txt`) and Microsoft Word (`.docx`).
- **Scene Header Matcher**: Case-insensitive regex matching line starts:
  `^(?:Scene|SCENE|scene)\s+(\d+)[:.]?`
- **Integrity Rules**:
  - Duplicate scene numbers: **HARD ERROR** (job halted immediately).
  - Missing scene numbers: **WARNING** logged, original scene numbers preserved.
  - Multi-paragraph descriptions, dialogues, and scene headings are preserved intact.

---

## 5. Output Reconciliation & DOCX Export

- Output scenes are matched against input scene identifiers.
- Prompts are extracted from `.result.structured_output.scenes`.
- Sorted strictly in ascending numerical order by canonical `scene_number`.
- Non-contiguous scene numbers are never renumbered or filled with dummy text.
- Exported DOCX formats each entry:
  ```text
  Scene 1: A completely textless hand-painted illustration with absolutely no words...
  Scene 2: A completely textless hand-painted illustration with absolutely no words...
  ```
