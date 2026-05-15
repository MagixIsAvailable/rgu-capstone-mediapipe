"""
Runtime hook to add ViGEm DLL directories from the PyInstaller extraction
so that ctypes and vgamepad can locate native DLLs at runtime.

This file is executed very early by PyInstaller (before application imports),
so it's the right place to call os.add_dll_directory for extracted DLLs.
"""
import os
import sys
from pathlib import Path
try:
    _meipass = getattr(sys, '_MEIPASS', None)
    if _meipass:
        base = Path(_meipass) / 'vgamepad' / 'win' / 'vigem' / 'client'
        # Add both x64 and x86 if present; order doesn't matter.
        for arch in ('x64', 'x86'):
            p = base / arch
            if p.exists():
                try:
                    os.add_dll_directory(str(p))
                except Exception:
                    # Older Python versions or restricted environments may fail;
                    # ignore and continue — importing vgamepad may still succeed.
                    pass
        # As a last-resort attempt, try to preload the ViGEmClient DLL via ctypes
        # so pyimod03_ctypes won't fail when vgamepad imports it.
        try:
            import ctypes
            dll = None
            for arch in ('x64', 'x86'):
                candidate = base / arch / 'ViGEmClient.dll'
                if candidate.exists():
                    try:
                        ctypes.CDLL(str(candidate))
                        dll = candidate
                        break
                    except Exception:
                        continue
        except Exception:
            pass
except Exception:
    # Keep runtime hook robust: any failure here shouldn't stop the app from
    # starting — vgamepad import may still succeed if Windows loader finds the
    # DLL via PATH or the system has ViGEm installed.
    pass