"""
Real Desktop App Launcher — Nightion Phase 30
Actually opens applications using subprocess.Popen.
"""
import subprocess
import time
import sys
import os
from typing import Dict, Any, List, Union, Optional

from action_schemas import ActionContract, OSActionType, ActionMode, ActionResponse
from capability_policy import PolicyState

# ── Resolve Windows username ONCE at module load ──────────────────────────────
_USERNAME: str = os.getenv("USERNAME") or os.getenv("USER") or "User"


def _u(path: str) -> str:
    """Expand {user} placeholder with the real Windows username."""
    return path.replace("{user}", _USERNAME)


# ── App Registry: name → executable (string or list for multi-arg commands) ───
# All {user} paths are expanded at module load via _u(). Never call _u() at
# launch time — it's already been applied here.
_AppEntry = Union[str, List[str]]

APP_REGISTRY: Dict[str, _AppEntry] = {
    # System Apps
    "notepad":           "notepad.exe",
    "calculator":        "calc.exe",
    "paint":             "mspaint.exe",
    "cmd":               "cmd.exe",
    "powershell":        "powershell.exe",
    "explorer":          "explorer.exe",
    "task manager":      "taskmgr.exe",
    "control panel":     "control.exe",
    "settings":          "ms-settings:",
    "camera":            "microsoft.windows.camera:",

    # Browsers
    "chrome":            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google chrome":     r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "firefox":           r"C:\Program Files\Mozilla Firefox\firefox.exe",
    "edge":              "msedge.exe",
    "microsoft edge":    "msedge.exe",
    "brave":             r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",

    # Dev Tools
    "vscode":            "code",
    "vs code":           "code",
    "visual studio code":"code",
    "git bash":          r"C:\Program Files\Git\git-bash.exe",
    "terminal":          "wt.exe",
    "windows terminal":  "wt.exe",

    # Media
    "vlc":               r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    "spotify":           _u(r"C:\Users\{user}\AppData\Roaming\Spotify\Spotify.exe"),
    "obs":               r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
    "steam":             r"C:\Program Files (x86)\Steam\steam.exe",

    # Office
    "word":              "WINWORD.EXE",
    "excel":             "EXCEL.EXE",
    "powerpoint":        "POWERPNT.EXE",

    # Misc
    "task scheduler":    "taskschd.msc",
    "regedit":           "regedit.exe",
    "snipping tool":     "snippingtool.exe",
    "sticky notes":      "stikynot.exe",
    "skype":             r"C:\Program Files (x86)\Microsoft\Skype for Desktop\Skype.exe",

    # Messaging (Phase 30)
    "whatsapp":          _u(r"C:\Users\{user}\AppData\Local\WhatsApp\WhatsApp.exe"),
    "whats app":         _u(r"C:\Users\{user}\AppData\Local\WhatsApp\WhatsApp.exe"),
    "telegram":          _u(r"C:\Users\{user}\AppData\Roaming\Telegram Desktop\Telegram.exe"),
    "zoom":              _u(r"C:\Users\{user}\AppData\Roaming\Zoom\bin\Zoom.exe"),
    "slack":             _u(r"C:\Users\{user}\AppData\Local\slack\slack.exe"),

    # Multi-arg entries stored as lists (Popen receives a list, never a bare string)
    "discord":           [
        _u(r"C:\Users\{user}\AppData\Local\Discord\Update.exe"),
        "--processStart",
        "Discord.exe",
    ],
    "teams":             [
        _u(r"C:\Users\{user}\AppData\Local\Microsoft\Teams\Update.exe"),
        "--processStart",
        "Teams.exe",
    ],
    "microsoft teams":   [
        _u(r"C:\Users\{user}\AppData\Local\Microsoft\Teams\Update.exe"),
        "--processStart",
        "Teams.exe",
    ],
}


def _find_app_dynamic(name: str) -> Optional[str]:
    """
    Dynamically resolve an app executable using:
      1. shutil.which  — already on PATH (e.g. code, wt)
      2. HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\<name>.exe
      3. Common per-user install dirs (AppData\\Local, AppData\\Roaming, Program Files)
    Returns a resolved path string, or None if not found.
    """
    import shutil
    # 1. PATH lookup
    found = shutil.which(name) or shutil.which(name + ".exe")
    if found:
        return found

    # 2. Windows Registry App Paths
    if sys.platform == "win32":
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for subkey in (
                f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{name}.exe",
                f"SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{name}.exe",
            ):
                try:
                    with winreg.OpenKey(hive, subkey) as k:
                        val, _ = winreg.QueryValueEx(k, "")
                        if val and os.path.isfile(val):
                            return val
                except OSError:
                    pass

    # 3. Common per-user install directories
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), name, f"{name}.exe"),
        os.path.join(os.environ.get("APPDATA", ""),      name, f"{name}.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), name.capitalize(), f"{name.capitalize()}.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    return None


def _resolve_app(name: str) -> "_AppEntry":
    """
    Find the best executable for a given app name.
    Priority: APP_REGISTRY static entry → dynamic winreg/PATH lookup → raw name.
    """
    name_lower = name.lower().strip()

    # 1. Direct registry match
    if name_lower in APP_REGISTRY:
        return APP_REGISTRY[name_lower]

    # 2. Partial match in registry
    for key, entry in APP_REGISTRY.items():
        if key in name_lower or name_lower in key:
            return entry

    # 3. Dynamic lookup (winreg + PATH) — handles apps not in the registry
    dynamic = _find_app_dynamic(name_lower)
    if dynamic:
        return dynamic

    # 4. Last resort: pass the raw name to Popen and let the OS handle it
    return name_lower


class DesktopActionManager:
    """
    Phase 33 — Real Native Desktop OS Controller.
    Launches applications, not just pretends to.
    """

    def __init__(self, policy: PolicyState):
        self.policy = policy
        self.action_history: List[ActionResponse] = []

    async def execute_native_action(self, contract: ActionContract) -> ActionResponse:
        start = time.time()

        if contract.action_type == OSActionType.OPEN_APP:
            return self._launch_app(contract, start)

        # Blocked for safety: destructive OS ops
        if contract.action_type == OSActionType.FILE_DELETE:
            return ActionResponse(
                trace_id=contract.trace_id,
                action_type=contract.action_type,
                status="BLOCKED",
                error="File deletion is disabled for safety.",
                execution_time_ms=0,
            )

        # Other actions (click, type) — mock for now but labeled honestly
        return ActionResponse(
            trace_id=contract.trace_id,
            action_type=contract.action_type,
            status="UNSUPPORTED",
            error=f"Action '{contract.action_type.value}' is not yet implemented.",
            execution_time_ms=int((time.time() - start) * 1000),
        )

    def _launch_app(self, contract: ActionContract, start: float) -> ActionResponse:
        """Really open an application. Handles both string and list-of-args entries."""
        app_input = (contract.payload or "").strip()
        entry = _resolve_app(app_input)

        try:
            if sys.platform != "win32":
                return ActionResponse(
                    trace_id=contract.trace_id,
                    action_type=contract.action_type,
                    status="UNSUPPORTED",
                    error="App launching is only supported on Windows.",
                    execution_time_ms=0,
                )

            if isinstance(entry, list):
                # Multi-arg launcher (e.g. Discord, Teams)
                subprocess.Popen(entry, shell=False)
            elif entry.endswith(":"):
                # UWP / protocol-handler (e.g. ms-settings:)
                subprocess.Popen(f"start {entry}", shell=True)
            elif entry.endswith(".msc"):
                subprocess.Popen(["mmc", entry], shell=False)
            else:
                subprocess.Popen(entry, shell=False)

            exe_display = entry[0] if isinstance(entry, list) else entry
            response = ActionResponse(
                trace_id=contract.trace_id,
                action_type=contract.action_type,
                status="SUCCESS",
                result_data={"app": app_input, "exe": exe_display},
                execution_time_ms=int((time.time() - start) * 1000),
            )
            self.action_history.append(response)
            return response

        except FileNotFoundError:
            exe_display = entry[0] if isinstance(entry, list) else entry
            return ActionResponse(
                trace_id=contract.trace_id,
                action_type=contract.action_type,
                status="FAILED",
                error=f"Could not find '{exe_display}'. Is '{app_input}' installed? "
                      f"Check that the app is installed for user '{_USERNAME}'.",
                execution_time_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return ActionResponse(
                trace_id=contract.trace_id,
                action_type=contract.action_type,
                status="FAILED",
                error=str(e),
                execution_time_ms=int((time.time() - start) * 1000),
            )
