# Prompt Generator Subsystem Architecture

## 1. Architectural Principles
1. **Instruction Immutability**: `instruction.txt` is an untouchable canonical artifact validated by SHA-256 before any job executes.
2. **Deterministic Schemas**: Zero fragile regex extractions on freeform LLM outputs; strictly schema-validated `structured_output.scenes`.
3. **Subprocess Isolation**: One fresh CLI process per batch of 15 scenes. No cross-batch conversational state.
4. **Decoupled Workflows**: Independent of downstream Flow Batch Manager tasks.
5. **No-Fallback Guarantees**: Strict halt on model unavailability or rate limiting without silent degradation.

---

## 2. Component Diagram

```
+-------------------------------------------------------------+
|                      Config & Integrity                     |
|  - ConfigManager (config/prompt_generator_config.json)      |
|  - IntegrityChecker (SHA-256 of instruction.txt)            |
+-------------------------------------------------------------+
                              │
                              ▼
+---------------------+   +---------------------+   +---------------------+
|    SceneParser      |──►|     BatchQueue      |──►| AntigravityCLIProv  |
|  - Regex line-start |   |  - BATCH_SIZE = 15  |   |  - Fresh process    |
|  - Sequence check   |   |  - Retry limit (3)  |   |  - Stdin streaming  |
|  - No renumbering   |   |  - Resume caching   |   |  - Schema validated |
+---------------------+   +---------------------+   +---------------------+
                                                               │
                                                               ▼
+---------------------+                             +---------------------+
|    DocxExporter     |◄────────────────────────────| ReconciliationEng   |
|  - Ordered export   |                             |  - Sort canonical ID|
|  - Standard labels  |                             |  - Loss detection   |
+---------------------+                             +---------------------+
```

---

## 3. Data Models (`src/prompt_generator/models.py`)

- **`Scene`**: `scene_number: int`, `raw_text: str`, `status: SceneStatus`, `generated_prompt: Optional[str]`, `error: Optional[str]`.
- **`Batch`**: `batch_id: str`, `batch_index: int`, `scenes: List[Scene]`, `status: BatchStatus`, `attempts: int`.
- **`PromptJob`**: `job_id: str`, `input_file: str`, `output_file: str`, `batches: List[Batch]`, `created_at: datetime`.
- **`QueueState`**: Enum (`IDLE`, `VALIDATING`, `QUEUED`, `RUNNING`, `SUCCESS`, `RETRYING`, `RATE_LIMITED`, `FAILED`, `CANCELLED`).

---

## 4. Batching & Subprocess Lifecycle

1. A script with $N$ scenes is divided into batches of size 15 ($\lceil N / 15 \rceil$ batches).
2. For each batch:
   - Verify SHA-256 hash of `instruction.txt`.
   - Launch fresh `agy` subprocess:
     ```powershell
     agy --model gemini-3.1-pro-high --effort high --input-format stream-json --output-format stream-json --print-timeout 10m --json-schema config/scene_schema.json
     ```
   - Stream verbatim `instruction.txt` + batch scenes over `stdin`.
   - Read output stream until terminal result is returned.
   - Extract `.result.structured_output.scenes`.
   - Terminate the subprocess cleanly.
3. On transient error: retry up to 3 times with exponential backoff.
4. On `RATE_LIMITED`: immediately halt, preserve incomplete batch, notify user, and await recovery without regenerating confirmed scenes.

---

## 5. Reconciliation Contract

- All batch responses are collected into a single dataset.
- The engine checks that every parsed input `scene_number` is present in the output.
- Scenes are sorted in strictly ascending numerical order by canonical `scene_number`.
- **Non-contiguous sequences are preserved** (e.g. 1, 2, 4, 5 are kept intact without renumbering or filling gaps).
- Formatted prompts are written to the target DOCX file.
