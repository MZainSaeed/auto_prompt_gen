# Antigravity CLI Provider Specification

## 1. Overview
The Antigravity CLI (`agy`) acts as the programmatic gateway to Google's generative models using cached local session credentials.
The Prompt Generator executes generation jobs using the following command signature:

```powershell
agy --model gemini-3.1-pro-high --effort high --input-format stream-json --output-format stream-json --print-timeout 10m --json-schema config/scene_schema.json
```

---

## 2. Command Flags & Requirements

| Flag | Value | Purpose |
|------|-------|---------|
| `--model` | `gemini-3.1-pro-high` | Explicit model selection; no silent fallback permitted. |
| `--effort` | `high` | Maximum reasoning depth; no silent downgrade permitted. |
| `--input-format` | `stream-json` | Enables piping large (>35KB) payloads over stdin. |
| `--output-format` | `stream-json` | **Mandatory pairing**: Streaming stdin requires streaming stdout. |
| `--print-timeout` | `10m` | Raises the CLI default 5m timeout to 10m to match app timeout. |
| `--json-schema` | `config/scene_schema.json` | Enforces rigid JSON output schema. |

---

## 3. Process Isolation Per Batch
- In `stream-json` mode, subsequent prompts in the same process are treated as a continuous conversation.
- To avoid token bloating, latency degradation, and cross-batch hallucination, **each 15-scene batch must spawn a fresh, dedicated CLI subprocess**.
- Upon receiving the final output for the batch, the subprocess is cleanly terminated.

---

## 4. Stdin Payload Format
The provider sends an NDJSON event to the subprocess `stdin`:
```json
{
  "event": "user",
  "message": {
    "content": "<VERBATIM_INSTRUCTION_TXT>\n\n<BATCH_SCENE_DATA>"
  }
}
```
- `<VERBATIM_INSTRUCTION_TXT>` contains the complete 35,545-byte instruction text.
- The stream is flushed and closed appropriately.

---

## 5. Output Extraction
The CLI outputs streaming NDJSON events. The provider monitors the stream until the terminal result event is received and extracts:
```json
.result.structured_output.scenes
```
Each scene object contains:
- `scene_number`: integer
- `prompt`: string

---

## 6. Standalone Quota & Usage Checks
- Interactive slash commands like `/usage` **cannot** be sent into an active `stream-json` session.
- To inspect quota and consumption, the provider runs a standalone headless command:
  ```powershell
  agy -p /usage
  ```
- Quota values are parsed dynamically; no quota limits are hard-coded.
