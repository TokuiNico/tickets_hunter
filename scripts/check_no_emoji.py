#!/usr/bin/env python3
"""Fail when any tracked .py file contains emoji.

Project rule (CONTRIBUTING.md): emoji are allowed in Markdown, never in
Python sources - they break cp950 consoles on Windows and PyInstaller logs.

Usage: python scripts/check_no_emoji.py [paths...]   (default: src tests benchmarks scripts)
"""
import os
import sys

DEFAULT_PATHS = ["src", "tests", "benchmarks", "scripts", "build_scripts"]

# Unicode blocks that only contain emoji / pictographs. CJK text, full-width
# punctuation and circled numbers (used by the captcha helpers) are outside
# these ranges on purpose.
EMOJI_RANGES = (
    (0x1F300, 0x1F5FF),  # Misc Symbols and Pictographs
    (0x1F600, 0x1F64F),  # Emoticons
    (0x1F680, 0x1F6FF),  # Transport and Map
    (0x1F700, 0x1F77F),  # Alchemical Symbols
    (0x1F900, 0x1F9FF),  # Supplemental Symbols and Pictographs
    (0x1FA70, 0x1FAFF),  # Symbols and Pictographs Extended-A
    (0x2600, 0x26FF),    # Misc Symbols (sun, umbrella, warning sign...)
    (0x2700, 0x2775),    # Dingbats (check marks, crosses, sparkles)
    (0x2794, 0x27BF),    # Dingbats, after the circled digits used by the captcha helpers
    (0x1F1E6, 0x1F1FF),  # Regional indicator (flags)
)
EXTRA_CODEPOINTS = {0x2B50, 0x2B55, 0x231A, 0x231B, 0x23E9, 0x23EA, 0x23F0, 0x23F3, 0x2934, 0x2935, 0x203C, 0x2049, 0x00A9, 0x00AE}


def is_emoji(char):
    cp = ord(char)
    if cp in EXTRA_CODEPOINTS and cp > 0x2000:
        return True
    return any(lo <= cp <= hi for lo, hi in EMOJI_RANGES)


def iter_python_files(paths):
    for path in paths:
        if os.path.isfile(path):
            if path.endswith(".py"):
                yield path
            continue
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d not in {".venv", "__pycache__", "node_modules", ".git"}]
            for name in filenames:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)


def main(argv):
    paths = argv[1:] or [p for p in DEFAULT_PATHS if os.path.exists(p)]
    problems = []
    for filepath in iter_python_files(paths):
        with open(filepath, encoding="utf-8", errors="replace") as handle:
            for lineno, line in enumerate(handle, 1):
                hits = [c for c in line if is_emoji(c)]
                if hits:
                    problems.append((filepath, lineno, "".join(hits), line.rstrip()))
    for filepath, lineno, hits, line in problems:
        print(f"{filepath}:{lineno}: emoji not allowed in .py files ({hits!r}): {line.strip()}")
    if problems:
        print(f"\n{len(problems)} line(s) with emoji. Move them to .md files or drop them.")
        return 1
    print("ok: no emoji in .py files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
