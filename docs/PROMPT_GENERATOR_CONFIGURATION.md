# Prompt Generator Configuration Reference

## 1. Canonical Configuration File
Path: `config/prompt_generator_config.json`

```json
{
  "prompt_generator": {
    "provider": "antigravity_cli",
    "executable": "agy",
    "model": "gemini-3.1-pro-high",
    "effort": "high",
    "batch_size": 15,
    "print_timeout": "10m",
    "timeout_minutes": 10,
    "max_retries": 3,
    "input_format": "stream-json",
    "output_format": "stream-json",
    "json_schema_file": "config/scene_schema.json",
    "instruction_file": "instruction.txt",
    "instruction_sha256": "1E8B4FE8F11C1B0625889855C765040E96761758735B32C4EC20E41301BDC007"
  }
}
```

---

## 2. Configuration Field Definitions

| Parameter | Type | Default / Locked | Description |
|-----------|------|------------------|-------------|
| `provider` | string | `"antigravity_cli"` | Must be `"antigravity_cli"`. Other providers rejected. |
| `executable` | string | `"agy"` | Path or command name for Antigravity CLI. |
| `model` | string | `"gemini-3.1-pro-high"` | **LOCKED**. No silent fallback permitted. |
| `effort` | string | `"high"` | **LOCKED**. Reasoning depth. Never reduced. |
| `batch_size` | integer | `15` | **LOCKED**. Number of scenes per CLI request. |
| `print_timeout` | string | `"10m"` | CLI argument overriding default 5m timeout. |
| `timeout_minutes`| integer | `10` | Subprocess wall-clock timeout in minutes. |
| `max_retries` | integer | `3` | Maximum automatic retries on transient errors. |
| `input_format` | string | `"stream-json"` | Subprocess input stream format. |
| `output_format` | string | `"stream-json"` | Subprocess output stream format (paired with input). |
| `json_schema_file` | string | `"config/scene_schema.json"` | Path to formal output schema. |
| `instruction_file` | string | `"instruction.txt"` | Authoritative prompt-generation instructions. |
| `instruction_sha256` | string | `"1E8B4FE8F...BDC007"` | Authoritative SHA-256 hash required for execution. |

---

## 3. Validation & Immutability Rules
- If `model != "gemini-3.1-pro-high"` or `effort != "high"`, the configuration validator rejects loading.
- If `batch_size != 15`, the configuration validator resets or rejects chunk modifications.
- If the SHA-256 hash of `instruction_file` differs from `instruction_sha256`, the engine aborts with `INSTRUCTION_INTEGRITY_ERROR`.
