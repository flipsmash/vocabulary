"""
Windows espeak fix utility
Import this module before using phonemizer to ensure espeak is found correctly
"""

import os
import shutil
import sys

# HARDCODED ESPEAK PATH FOR WINDOWS
ESPEAK_PATH = r"C:\Program Files (x86)\eSpeak\command_line\espeak.exe"
ESPEAK_DIR = r"C:\Program Files (x86)\eSpeak\command_line"

# Flag to ensure we only apply the fix once
_fix_applied = False


def apply_espeak_fix():
    """Apply the espeak fix for Windows"""
    global _fix_applied

    if _fix_applied:
        return

    print("Applying Windows espeak fix...")

    # Set up environment
    original_path = os.environ.get('PATH', '')
    if ESPEAK_DIR not in original_path:
        os.environ['PATH'] = ESPEAK_DIR + os.pathsep + original_path

    espeak_data_path = r"C:\Program Files (x86)\eSpeak\espeak-data"
    if os.path.exists(espeak_data_path):
        os.environ['ESPEAK_DATA_PATH'] = espeak_data_path

    # Monkey patch shutil.which to always return our espeak path
    original_which = shutil.which

    def patched_which(cmd, mode=os.F_OK | os.X_OK, path=None):
        if cmd == 'espeak' or cmd == 'espeak.exe':
            return ESPEAK_PATH
        return original_which(cmd, mode, path)

    shutil.which = patched_which

    _fix_applied = True
    print("✓ Espeak fix applied")


# Apply the fix automatically when this module is imported
apply_espeak_fix()
