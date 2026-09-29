"""Account Manager for Antigravity CLI credential switching.

Implements filesystem-level account switching by snapshotting and restoring
the ~/.gemini/antigravity-cli/ credential directory.
"""

import json
import shutil
import subprocess
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Files to snapshot per account (excludes large conversation DB)
SNAPSHOT_FILES = [
    "jetski_state.pbtxt",
    "settings.json",
    "last_check.timestamp",
    "installation_id",
]

AGY_CLI_DIR = Path.home() / ".gemini" / "antigravity-cli"
ACCOUNTS_ROOT = Path.home() / ".gemini" / "agy_accounts"
ACCOUNTS_JSON = ACCOUNTS_ROOT / "accounts.json"

AGY_EXECUTABLE = None


def _find_agy() -> str:
    """Locate the agy executable across Windows and macOS."""
    global AGY_EXECUTABLE
    if AGY_EXECUTABLE:
        return AGY_EXECUTABLE
    found = shutil.which("agy")
    if not found:
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
        for c in candidates:
            if c.is_file():
                found = str(c)
                break
    AGY_EXECUTABLE = found or "agy"
    return AGY_EXECUTABLE


# --------------------------------------------------------------------------- #
#  Data model                                                                  #
# --------------------------------------------------------------------------- #

class Account:
    def __init__(self, name: str, label: str, created_at: str, is_active: bool = False):
        self.name = name          # filesystem-safe identifier
        self.label = label        # human display label (e.g. email)
        self.created_at = created_at
        self.is_active = is_active

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "created_at": self.created_at,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Account":
        return cls(
            name=d["name"],
            label=d.get("label", d["name"]),
            created_at=d.get("created_at", ""),
            is_active=d.get("is_active", False),
        )


# --------------------------------------------------------------------------- #
#  AccountManager                                                              #
# --------------------------------------------------------------------------- #

class AccountManager:
    """Manages multiple AGY credential snapshots and handles switching."""

    def __init__(self):
        ACCOUNTS_ROOT.mkdir(parents=True, exist_ok=True)
        self._ensure_accounts_json()

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _ensure_accounts_json(self):
        """Create accounts.json with the current session as default if missing."""
        if not ACCOUNTS_JSON.exists():
            data = {"active": None, "accounts": []}
            with open(ACCOUNTS_JSON, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

    def _load_data(self) -> dict:
        try:
            with open(ACCOUNTS_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"active": None, "accounts": []}

    def _save_data(self, data: dict):
        with open(ACCOUNTS_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _snapshot_dir(self, name: str) -> Path:
        d = ACCOUNTS_ROOT / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def list_accounts(self) -> List[Account]:
        """Return all saved accounts."""
        data = self._load_data()
        active_name = data.get("active")
        accounts = []
        for a in data.get("accounts", []):
            acc = Account.from_dict(a)
            acc.is_active = acc.name == active_name
            accounts.append(acc)
        return accounts

    def get_active_account(self) -> Optional[Account]:
        """Return currently active account, or None if not saved."""
        for acc in self.list_accounts():
            if acc.is_active:
                return acc
        return None

    def save_current_as_account(self, name: str, label: str) -> Account:
        """Snapshot the current ~/.gemini/antigravity-cli/ as a named account."""
        snap_dir = self._snapshot_dir(name)

        # Copy snapshot files
        for fname in SNAPSHOT_FILES:
            src = AGY_CLI_DIR / fname
            if src.exists():
                shutil.copy2(src, snap_dir / fname)

        # Copy any token/auth files (anything not a .db or .log)
        for item in AGY_CLI_DIR.iterdir():
            if item.is_file() and item.suffix not in (".db", ".log") and item.name not in SNAPSHOT_FILES:
                try:
                    shutil.copy2(item, snap_dir / item.name)
                except Exception:
                    pass

        created_at = datetime.now(timezone.utc).isoformat()
        acc = Account(name=name, label=label, created_at=created_at, is_active=False)

        data = self._load_data()
        # Remove existing entry with same name
        data["accounts"] = [a for a in data["accounts"] if a["name"] != name]
        data["accounts"].append(acc.to_dict())
        self._save_data(data)
        return acc

    def switch_account(self, name: str) -> bool:
        """Switch to a saved account by restoring its snapshot.

        Returns True on success, False on failure.
        """
        snap_dir = self._snapshot_dir(name)
        if not snap_dir.exists():
            logger.error(f"Account snapshot not found: {name}")
            return False

        # Restore snapshot files to AGY_CLI_DIR
        restored_any = False
        for item in snap_dir.iterdir():
            if item.is_file():
                try:
                    shutil.copy2(item, AGY_CLI_DIR / item.name)
                    restored_any = True
                except Exception as e:
                    logger.warning(f"Could not restore {item.name}: {e}")

        if not restored_any:
            return False

        # Mark active in accounts.json
        data = self._load_data()
        data["active"] = name
        # Update is_active flags in list
        for a in data["accounts"]:
            a["is_active"] = a["name"] == name
        self._save_data(data)

        logger.info(f"Switched to account: {name}")
        return True

    def delete_account(self, name: str):
        """Delete a saved account snapshot."""
        snap_dir = self._snapshot_dir(name)
        if snap_dir.exists():
            shutil.rmtree(snap_dir, ignore_errors=True)
        data = self._load_data()
        data["accounts"] = [a for a in data["accounts"] if a["name"] != name]
        if data.get("active") == name:
            data["active"] = None
        self._save_data(data)

    def verify_current_auth(self) -> bool:
        """Quickly verify the current agy session is authenticated."""
        try:
            agy = _find_agy()
            r = subprocess.run(
                [agy, "models"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return r.returncode == 0 and len(r.stdout.strip()) > 0
        except Exception:
            return False

    def get_current_email_hint(self) -> str:
        """Try to derive the current account label from agy -p /whoami output."""
        try:
            agy = _find_agy()
            r = subprocess.run(
                [agy, "-p", "/whoami"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if r.returncode == 0 and r.stdout.strip():
                # Parse email-like pattern from response
                m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", r.stdout)
                if m:
                    return m.group(0)
                # Return first line of meaningful output
                for line in r.stdout.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and len(line) < 80:
                        return line
        except Exception:
            pass
        return "Current Session"

    def launch_login_terminal(self):
        """Open a new terminal window for the user to run agy interactively."""
        import platform, subprocess
        agy = _find_agy()
        system = platform.system()

        if system == 'Windows':
            instructions = (
                "Write-Host '===========================================================' -ForegroundColor Cyan; "
                "Write-Host ' To log into a NEW account, type: /switch-account' -ForegroundColor Yellow; "
                "Write-Host ' After logging in, simply close this window and refresh the UI.' -ForegroundColor Cyan; "
                "Write-Host '===========================================================' -ForegroundColor Cyan; "
                f"& '{agy}'"
            )
            subprocess.Popen(
                ["powershell", "-NoExit", "-Command", instructions],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
        elif system == 'Darwin':
            # macOS Terminal.app via osascript
            apple_script = f'''
tell application "Terminal"
    activate
    do script "echo '==========================================================='; echo ' To log into a NEW account, type: /switch-account'; echo ' After logging in, simply close this window and refresh the UI.'; echo '==========================================================='; '{agy}'"
end tell
'''
            subprocess.Popen(["osascript", "-e", apple_script])
        else:
            # Linux fallback
            subprocess.Popen(["x-terminal-emulator", "-e", f"{agy}"])


# --------------------------------------------------------------------------- #
#  Quota parsing                                                               #
# --------------------------------------------------------------------------- #

class QuotaInfo:
    def __init__(self):
        self.gemini_weekly_pct: Optional[float] = None
        self.gemini_five_hour_pct: Optional[float] = None
        self.claude_weekly_pct: Optional[float] = None
        self.claude_five_hour_pct: Optional[float] = None
        self.raw: str = ""
        self.error: str = ""

    def overall_gemini_pct(self) -> Optional[float]:
        """Return the more restrictive of the two Gemini quota limits."""
        vals = [v for v in [self.gemini_weekly_pct, self.gemini_five_hour_pct] if v is not None]
        return min(vals) if vals else None

    def status_label(self) -> str:
        pct = self.overall_gemini_pct()
        if pct is None:
            return "Unknown"
        if pct > 50:
            return "Good"
        if pct > 15:
            return "Low"
        return "Critical"


def fetch_quota() -> QuotaInfo:
    """Run 'agy -p /usage' and parse the tab-delimited quota output."""
    info = QuotaInfo()
    try:
        agy = _find_agy()
        r = subprocess.run(
            [agy, "-p", "/usage"],
            capture_output=True,
            text=True,
            timeout=25,
        )
        info.raw = r.stdout.strip()
        for line in r.stdout.splitlines():
            parts = [p.strip() for p in line.split("\t")]
            if len(parts) < 3:
                continue
            category = parts[0].lower()
            limit_type = parts[1].lower()
            pct_str = parts[2].replace("%", "").strip()
            try:
                pct = float(pct_str)
            except ValueError:
                continue

            is_gemini = "gemini" in category
            is_claude = "claude" in category or "gpt" in category
            is_weekly = "weekly" in limit_type
            is_five_hour = "five" in limit_type or "5" in limit_type

            if is_gemini and is_weekly:
                info.gemini_weekly_pct = pct
            elif is_gemini and is_five_hour:
                info.gemini_five_hour_pct = pct
            elif is_claude and is_weekly:
                info.claude_weekly_pct = pct
            elif is_claude and is_five_hour:
                info.claude_five_hour_pct = pct

    except subprocess.TimeoutExpired:
        info.error = "Quota check timed out"
    except Exception as e:
        info.error = str(e)

    return info
