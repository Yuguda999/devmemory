"""Install ``devmemory watch`` as a background service so it survives reboots.

- Linux  : systemd *user* unit (``~/.config/systemd/user/devmemory-watch.service``).
- macOS  : launchd LaunchAgent (``~/Library/LaunchAgents/io.devmemory.watch.plist``).
- Windows: prints a Task Scheduler command (no reliable headless install).

Everything is best-effort and idempotent: failures return a message and never
raise, so wiring this into ``devmemory install`` can't break the install.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

SERVICE_NAME = "devmemory-watch"
_PLIST_LABEL = "io.devmemory.watch"


def _devmemory_bin() -> str:
    return shutil.which("devmemory") or "devmemory"


# ── Linux / systemd ─────────────────────────────────────────────────────────


def _systemd_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{SERVICE_NAME}.service"


def _has_systemd() -> bool:
    return shutil.which("systemctl") is not None and Path("/run/systemd/system").exists()


def _install_systemd(host: str | None) -> tuple[bool, str]:
    env_line = f"Environment=DEVMEMORY_HOST={host}\n" if host else ""
    unit = (
        "[Unit]\n"
        "Description=DevMemory watch — auto-save AI tool conversations\n"
        "After=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={_devmemory_bin()} watch\n"
        f"{env_line}"
        "Restart=on-failure\n"
        "RestartSec=10\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
    path = _systemd_unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(unit, encoding="utf-8")

    if not _has_systemd():
        return True, (
            f"Wrote {path}, but systemd isn't running here. Start the daemon manually:\n"
            "     nohup devmemory watch >/dev/null 2>&1 &"
        )
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, timeout=15)
        r = subprocess.run(
            ["systemctl", "--user", "enable", "--now", f"{SERVICE_NAME}.service"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode == 0:
            return True, (
                f"systemd user service enabled + started ({path}). "
                f"Check: systemctl --user status {SERVICE_NAME}"
            )
        return True, (
            f"Wrote {path}, but enabling failed ({r.stderr.strip()[:160]}). "
            "You may need `loginctl enable-linger $USER`, then:\n"
            f"     systemctl --user enable --now {SERVICE_NAME}"
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return True, (
            f"Wrote {path}; enable manually (systemctl --user enable --now {SERVICE_NAME}): {exc}"
        )


# ── macOS / launchd ───────────────────────────────────────────────────────────


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_PLIST_LABEL}.plist"


def _install_launchd(host: str | None) -> tuple[bool, str]:
    env_block = ""
    if host:
        env_block = (
            "    <key>EnvironmentVariables</key>\n"
            "    <dict>\n"
            f"      <key>DEVMEMORY_HOST</key><string>{host}</string>\n"
            "    </dict>\n"
        )
    plist = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "  <dict>\n"
        f"    <key>Label</key><string>{_PLIST_LABEL}</string>\n"
        "    <key>ProgramArguments</key>\n"
        f"    <array><string>{_devmemory_bin()}</string><string>watch</string></array>\n"
        "    <key>RunAtLoad</key><true/>\n"
        "    <key>KeepAlive</key><true/>\n"
        f"{env_block}"
        "  </dict>\n"
        "</plist>\n"
    )
    path = _plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plist, encoding="utf-8")
    try:
        # Reload if already loaded, then load.
        subprocess.run(
            ["launchctl", "unload", str(path)], check=False, capture_output=True, timeout=15
        )
        r = subprocess.run(
            ["launchctl", "load", "-w", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode == 0:
            return True, f"launchd agent loaded ({path})."
        return True, f"Wrote {path}; load manually: launchctl load -w {path}"
    except (OSError, subprocess.SubprocessError) as exc:
        return True, f"Wrote {path}; load manually (launchctl load -w {path}): {exc}"


# ── Public API ────────────────────────────────────────────────────────────────


def install_service(host: str | None = None) -> tuple[bool, str]:
    """Install + start the watch background service for the current OS."""
    system = platform.system()
    if system == "Linux":
        return _install_systemd(host)
    if system == "Darwin":
        return _install_launchd(host)
    if system == "Windows":
        return True, (
            "Windows: register a startup task with:\n"
            '     schtasks /Create /SC ONLOGON /TN DevMemoryWatch /TR "devmemory watch" /F'
        )
    return False, f"Unsupported OS for service install: {system}"
