# Prompt Generator Troubleshooting & Error Codes

## Standardized Error Codes & Triage

### 1. `CLI_NOT_FOUND`
- **Cause**: The `agy` executable is not installed or not in system PATH.
- **Triage**: Verify `agy --version` runs in PowerShell. Ensure Antigravity IDE / CLI is installed.

---

### 2. `CLI_NOT_AUTHENTICATED`
- **Cause**: No active Google account session found in local CLI cache.
- **Triage**: Run `agy auth login` or launch the Antigravity IDE to establish account credentials.

---

### 3. `MODEL_UNAVAILABLE`
- **Cause**: `gemini-3.1-pro-high` is temporarily inaccessible or missing from provider listings.
- **Policy**: Halt immediately. Never silently switch to Flash, 2.5 Pro, Claude, or GPT.
- **Triage**: Run `agy models` to check current provider model availability.

---

### 4. `RATE_LIMITED`
- **Cause**: Rate limit or quota exhaustion reached for `gemini-3.1-pro-high`.
- **Policy**:
  1. Immediately stop launching new generation requests.
  2. Do not switch models or providers.
  3. Do not reduce effort from `high`.
  4. Preserve incomplete batch state.
  5. Show notification: `"Gemini 3.1 Pro High quota/rate limit reached."`.
  6. Inspect quota via standalone command: `agy -p /usage`.
  7. Await legitimate reset before resuming. Confirmed scenes are never regenerated.
- **Classification**: Distinguish temporary rate limit, five-hour quota, weekly quota, model unavailable, and auth failure.

---

### 5. `INVALID_OUTPUT`
- **Cause**: The CLI response failed JSON schema validation or `.result.structured_output.scenes` was malformed.
- **Triage**: Subprocess will automatically retry up to 3 times before halting for manual review.

---

### 6. `INSTRUCTION_INTEGRITY_ERROR`
- **Cause**: The SHA-256 hash of `instruction.txt` did not match `1E8B4FE8F11C1B0625889855C765040E96761758735B32C4EC20E41301BDC007`.
- **Policy**: Never attempt automated repair. Halt immediately.
- **Triage**: Restore `instruction.txt` from original source control.

---

### 7. `OUTPUT_INTEGRITY_ERROR`
- **Cause**: Reconciliation detected missing scenes, duplicate scene outputs, or unexplained scene drops.
- **Triage**: Check batch logs to identify which batch failed, review cache state, and resume failed batch.
