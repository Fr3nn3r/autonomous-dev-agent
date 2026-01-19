"""Utilities for finding and invoking external CLI tools.

Provides robust cross-platform discovery of CLI executables,
particularly for the Claude CLI which has platform-specific installation paths.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Optional


def find_claude_executable() -> Optional[str]:
    """Find the Claude CLI executable.

    Searches in order:
    1. PATH (via shutil.which)
    2. Windows-specific: .cmd extension, npm global locations
    3. Unix-specific: common installation directories

    Returns:
        Path to the claude executable, or None if not found.
    """
    # Try shutil.which first (respects PATH)
    claude_path = shutil.which("claude")
    if claude_path:
        return claude_path

    # On Windows, try .cmd extension
    if sys.platform == "win32":
        claude_path = shutil.which("claude.cmd")
        if claude_path:
            return claude_path

        # Check common npm global locations on Windows
        npm_paths = [
            Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
            Path(os.environ.get("LOCALAPPDATA", "")) / "npm" / "claude.cmd",
            Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd",
            # nvm for Windows puts binaries here
            Path(os.environ.get("NVM_SYMLINK", "")) / "claude.cmd" if os.environ.get("NVM_SYMLINK") else None,
        ]
        for p in npm_paths:
            if p and p.exists():
                return str(p)

    # On Unix, check common locations
    else:
        unix_paths = [
            Path.home() / ".npm-global" / "bin" / "claude",
            Path("/usr/local/bin/claude"),
            Path.home() / ".local" / "bin" / "claude",
            # nvm puts binaries in versioned directories, but also symlinks
            Path.home() / ".nvm" / "current" / "bin" / "claude",
        ]
        for p in unix_paths:
            if p.exists():
                return str(p)

    return None


def get_claude_executable() -> str:
    """Get the Claude CLI executable path, raising if not found.

    Returns:
        Path to the claude executable.

    Raises:
        FileNotFoundError: If Claude CLI is not installed or not in PATH.
    """
    exe = find_claude_executable()
    if exe is None:
        raise FileNotFoundError(
            "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code\n"
            "After installing, you may need to restart your terminal for PATH changes to take effect."
        )
    return exe


def is_claude_available() -> bool:
    """Check if Claude CLI is available.

    Returns:
        True if Claude CLI is found, False otherwise.
    """
    return find_claude_executable() is not None
