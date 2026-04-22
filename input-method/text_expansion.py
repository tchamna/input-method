import argparse
import csv
import datetime
import re
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional

import os
import tempfile

_LOCK_PATH = str(Path(tempfile.gettempdir()) / "TextExpander.lock")

def _acquire_single_instance_lock() -> None:
    """Exit immediately if another instance is already running (Windows only)."""
    try:
        import ctypes
        import ctypes.wintypes
        kernel32 = ctypes.windll.kernel32
        # Must declare restype as HANDLE (void*) or truncation gives wrong -1 compare
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD,
            ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD,
            ctypes.c_void_p,
        ]
        GENERIC_READ = 0x80000000
        FILE_SHARE_NONE = 0
        OPEN_ALWAYS = 4
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value  # 0xFFFF...FFFF on 64-bit
        handle = kernel32.CreateFileW(
            _LOCK_PATH, GENERIC_READ, FILE_SHARE_NONE, None, OPEN_ALWAYS, 0, None
        )
        if handle is None or handle == INVALID_HANDLE_VALUE:
            print("Text expander is already running. Only one instance allowed.")
            sys.exit(0)
        # Keep handle alive for the lifetime of the process.
        globals()["_LOCK_HANDLE"] = handle
    except (AttributeError, OSError):
        pass  # Non-Windows; skip guard

SHORTCUTS: Dict[str, str] = {
    "asap": "as soon as possible",
    "nj": "New Jersey",
    "@nj": "@njsharingnetwork",
}

TOGGLE_WINDOW_SECONDS = 0.35
SHIFT_KEYS = {"shift", "left shift", "right shift"}
SHIFT_SCAN_CODES = {42, 54}
DELIMITERS = {"space", "enter", "tab"}
WORD_TRIGGERS = ["space", "tab"]
MODIFIER_KEYS = {
    "alt",
    "left alt",
    "right alt",
    "ctrl",
    "left ctrl",
    "right ctrl",
    "windows",
    "left windows",
    "right windows",
}
NAVIGATION_KEYS = {
    "left",
    "right",
    "up",
    "down",
    "home",
    "end",
    "page up",
    "page down",
    "insert",
    "delete",
    "esc",
}


def _build_shortcut_pattern(shortcuts: Dict[str, str]) -> str:
    # Match longer keys first so specific shortcuts (e.g., @nj) beat generic ones (e.g., nj).
    parts = []
    for key in sorted(shortcuts.keys(), key=len, reverse=True):
        escaped_key = re.escape(key)

        prefix_boundary = r"(?<!\w)" if (key[0].isalnum() or key[0] == "_") else ""
        suffix_boundary = r"(?!\w)" if (key[-1].isalnum() or key[-1] == "_") else ""

        parts.append(prefix_boundary + escaped_key + suffix_boundary)

    return "(?:" + "|".join(parts) + ")"


def expand_shortcuts(text: str, shortcuts: Dict[str, str]) -> str:
    if not shortcuts:
        return text

    pattern = _build_shortcut_pattern(shortcuts)

    def replacer(match: re.Match) -> str:
        word = match.group(0)
        return shortcuts.get(word, word)

    return re.sub(pattern, replacer, text)


def parse_text_shortcuts(text_pairs: str) -> Dict[str, str]:
    """Parse text pairs in this format: key=value;key2=value2"""
    parsed: Dict[str, str] = {}
    if not text_pairs:
        return parsed

    for raw_pair in text_pairs.split(";"):
        pair = raw_pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ValueError(f"Invalid pair '{pair}'. Expected key=value format.")

        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            raise ValueError(f"Invalid pair '{pair}'. Shortcut key is empty.")
        parsed[key] = value

    return parsed


def load_shortcuts_from_csv(csv_path: Path) -> Dict[str, str]:
    """
    Load shortcuts from CSV.
    Supports either:
    - headers: shortcut,expansion
    - first two columns per row
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    parsed: Dict[str, str] = {}

    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        rows = [row for row in reader if row and any(cell.strip() for cell in row)]

    if not rows:
        return parsed

    first_row = [cell.strip().lower() for cell in rows[0]]
    has_named_columns = "shortcut" in first_row and "expansion" in first_row

    if has_named_columns:
        with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
            dict_reader = csv.DictReader(handle)
            for row in dict_reader:
                if not row:
                    continue
                key = (row.get("shortcut") or "").strip()
                value = (row.get("expansion") or "").strip()
                if key:
                    parsed[key] = value
        return parsed

    for row in rows:
        if len(row) < 2:
            continue
        key = row[0].strip()
        value = row[1].strip()
        if key:
            parsed[key] = value

    return parsed


def load_shortcuts_from_text_file(text_file: Path) -> Dict[str, str]:
    """Load shortcuts from text file with one key=value pair per line."""
    if not text_file.exists():
        raise FileNotFoundError(f"Text file not found: {text_file}")

    parsed: Dict[str, str] = {}
    for raw_line in text_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid line '{line}'. Expected key=value format.")

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            parsed[key] = value

    return parsed


def build_shortcuts(
    csv_file: Optional[str], text_pairs: Optional[str], text_file: Optional[str]
) -> Dict[str, str]:
    merged: Dict[str, str] = dict(SHORTCUTS)

    if csv_file:
        merged.update(load_shortcuts_from_csv(Path(csv_file)))
    if text_pairs:
        merged.update(parse_text_shortcuts(text_pairs))
    if text_file:
        merged.update(load_shortcuts_from_text_file(Path(text_file)))

    if not merged:
        raise ValueError("No shortcuts configured.")

    return merged


def find_default_shortcut_file(filename: str) -> Optional[str]:
    candidate_dirs = []

    if getattr(sys, "frozen", False):
        candidate_dirs.append(Path(sys.executable).resolve().parent)

    candidate_dirs.extend([Path.cwd(), Path(__file__).resolve().parent])

    seen_dirs = set()
    for directory in candidate_dirs:
        resolved_dir = directory.resolve()
        if resolved_dir in seen_dirs:
            continue
        seen_dirs.add(resolved_dir)

        candidate = resolved_dir / filename
        if candidate.exists():
            return str(candidate)

    return None


def _build_reloadable_shortcuts_loader(
    csv_file: Optional[str], text_pairs: Optional[str], text_file: Optional[str]
):
    tracked_files = [
        Path(file_path)
        for file_path in (csv_file, text_file)
        if file_path
    ]
    last_seen_tokens: Optional[tuple[tuple[str, int, int], ...]] = None

    def read_current_shortcuts() -> Dict[str, str]:
        return build_shortcuts(csv_file, text_pairs, text_file)

    def get_change_token() -> Optional[tuple[tuple[str, int, int], ...]]:
        if not tracked_files:
            return None

        snapshot = []
        for file_path in tracked_files:
            stat_result = file_path.stat()
            snapshot.append(
                (
                    str(file_path.resolve()),
                    stat_result.st_mtime_ns,
                    stat_result.st_size,
                )
            )
        return tuple(snapshot)

    def load_if_changed(force: bool = False) -> Optional[Dict[str, str]]:
        nonlocal last_seen_tokens

        current_tokens = get_change_token()
        if not force and current_tokens == last_seen_tokens:
            return None

        shortcuts = read_current_shortcuts()
        last_seen_tokens = current_tokens
        return shortcuts

    return load_if_changed


def run_global_expander(
    shortcuts: Dict[str, str],
    csv_file: Optional[str] = None,
    text_pairs: Optional[str] = None,
    text_file: Optional[str] = None,
    debug_log_path: Optional[str] = None,
) -> None:
    try:
        import keyboard
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'keyboard'. Install it with: pip install keyboard"
        ) from exc

    reload_shortcuts = _build_reloadable_shortcuts_loader(csv_file, text_pairs, text_file)
    enabled = True
    recent_shift_release_time = 0.0
    active_shortcuts = dict(shortcuts)
    typed_buffer = ""
    handling_replacement = False
    ctrl_active = False
    alt_active = False
    win_active = False
    quit_requested = threading.Event()
    debug_lock = threading.Lock()

    def log_debug(message: str) -> None:
        if not debug_log_path:
            return

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        log_file = Path(debug_log_path)
        with debug_lock:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(f"{timestamp} {message}\\n")

    def sorted_shortcuts() -> list[tuple[str, str]]:
        return sorted(active_shortcuts.items(), key=lambda item: len(item[0]), reverse=True)

    def current_state_label() -> str:
        return "ON" if enabled else "OFF"

    def is_shift_event(event: keyboard.KeyboardEvent) -> bool:
        name = (event.name or "").lower()
        if name in SHIFT_KEYS or "shift" in name:
            return True

        return event.scan_code in SHIFT_SCAN_CODES

    def replace_word(source_text: str, replacement_text: str) -> None:
        log_debug(f"replace start source={source_text!r} replacement={replacement_text!r}")
        for _ in range(len(source_text) + 1):
            keyboard.send("backspace")
        keyboard.write(replacement_text)
        log_debug("replace done")

    def matches_shortcut(buffer: str, shortcut: str) -> bool:
        if len(buffer) < len(shortcut):
            return False

        candidate = buffer[-len(shortcut):]
        return candidate.lower() == shortcut.lower()

    def maybe_expand_typed_buffer() -> None:
        nonlocal typed_buffer, handling_replacement
        if not enabled or not typed_buffer:
            log_debug(f"skip expand enabled={enabled} buffer={typed_buffer!r}")
            typed_buffer = ""
            return

        log_debug(f"check expand buffer={typed_buffer!r}")
        for source, replacement in sorted_shortcuts():
            if not matches_shortcut(typed_buffer, source):
                continue

            log_debug(f"match source={source!r} buffer={typed_buffer!r}")
            handling_replacement = True
            try:
                replace_word(source, replacement)
            finally:
                handling_replacement = False
            break

        typed_buffer = ""

    def enable_shortcuts() -> None:
        return

    def disable_shortcuts() -> None:
        nonlocal typed_buffer
        typed_buffer = ""

    def track_typed_shortcuts(event: keyboard.KeyboardEvent) -> None:
        nonlocal typed_buffer, ctrl_active, alt_active, win_active
        if handling_replacement:
            return

        name = (event.name or "")
        lowered = name.lower()

        if lowered in {"ctrl", "left ctrl", "right ctrl"}:
            ctrl_active = event.event_type == "down"
            if ctrl_active:
                typed_buffer = ""
                log_debug("buffer reset by ctrl modifier")
            return

        if lowered in {"alt", "left alt", "right alt"}:
            alt_active = event.event_type == "down"
            if alt_active:
                typed_buffer = ""
                log_debug("buffer reset by alt modifier")
            return

        if lowered in {"windows", "left windows", "right windows"}:
            win_active = event.event_type == "down"
            if win_active:
                typed_buffer = ""
                log_debug("buffer reset by windows modifier")
            return

        if event.event_type != "down":
            return

        log_debug(
            f"event name={name!r} lowered={lowered!r} "
            f"buffer_before={typed_buffer!r} modifiers=(ctrl={ctrl_active},alt={alt_active},win={win_active})"
        )

        if lowered in SHIFT_KEYS:
            return

        if ctrl_active or alt_active or win_active:
            typed_buffer = ""
            log_debug("buffer reset by active modifier combo")
            return

        if lowered in WORD_TRIGGERS:
            maybe_expand_typed_buffer()
            return

        if lowered == "backspace":
            typed_buffer = typed_buffer[:-1]
            log_debug(f"buffer backspace -> {typed_buffer!r}")
            return

        if lowered in NAVIGATION_KEYS:
            typed_buffer = ""
            log_debug("buffer reset by navigation key")
            return

        if len(name) == 1:
            typed_buffer += name
            if len(typed_buffer) > 100:
                typed_buffer = typed_buffer[-100:]
            log_debug(f"buffer append -> {typed_buffer!r}")
            return

        # Non-printable keys reset the current token.
        typed_buffer = ""
        log_debug("buffer reset by non-printable key")

    def refresh_shortcuts_if_needed() -> None:
        nonlocal active_shortcuts

        try:
            refreshed_shortcuts = reload_shortcuts()
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Shortcut reload skipped: {exc}")
            return

        if refreshed_shortcuts is None or refreshed_shortcuts == active_shortcuts:
            return

        was_enabled = enabled
        if was_enabled:
            disable_shortcuts()

        active_shortcuts = refreshed_shortcuts

        if was_enabled:
            enable_shortcuts()

        print(f"Reloaded {len(active_shortcuts)} shortcuts.")
        log_debug(f"reloaded shortcuts count={len(active_shortcuts)}")

    def toggle_if_double_shift(event: keyboard.KeyboardEvent) -> None:
        nonlocal enabled, recent_shift_release_time
        if event.event_type != "up":
            return
        if not is_shift_event(event):
            return

        now = time.monotonic()
        if now - recent_shift_release_time <= TOGGLE_WINDOW_SECONDS:
            enabled = not enabled
            if enabled:
                enable_shortcuts()
            else:
                disable_shortcuts()
            print(f"Text expander: {current_state_label()}")
            log_debug(f"toggle state={current_state_label()}")
            recent_shift_release_time = 0.0
            return

        recent_shift_release_time = now

    enable_shortcuts()
    keyboard.hook(toggle_if_double_shift)
    keyboard.hook(track_typed_shortcuts)

    print("Global text expander is running.")
    print("Type a shortcut and press Space or Tab to expand.")
    print("Double Shift quickly to toggle ON/OFF.")
    print("Press Ctrl+Alt+Q to quit.")
    if debug_log_path:
        print(f"Debug logging to: {debug_log_path}")
        log_debug("debug logging enabled")

    keyboard.add_hotkey("ctrl+alt+q", quit_requested.set)

    while not quit_requested.wait(0.25):
        refresh_shortcuts_if_needed()

    disable_shortcuts()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Global text expander")
    parser.add_argument(
        "--global",
        dest="global_mode",
        action="store_true",
        help="Run global text expander mode",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Path to a CSV file of shortcuts (defaults to local shortcuts.csv if present)",
    )
    parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="Inline shortcuts as key=value;key2=value2",
    )
    parser.add_argument(
        "--text-file",
        type=str,
        default=None,
        help="Path to a text file with one key=value shortcut per line",
    )
    parser.add_argument(
        "--debug-log",
        type=str,
        default=None,
        help="Optional path to write debug key-event logs",
    )
    parser.add_argument(
        "--build-share",
        type=str,
        metavar="OUTPUT_DIR",
        default=None,
        help="Build a shareable folder with the exe and shortcut files",
    )
    return parser.parse_args(argv)


def build_share_folder(output_dir: str) -> None:
    import shutil

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if getattr(sys, "frozen", False):
        exe_src = Path(sys.executable)
    else:
        exe_src = Path(sys.executable).parent / "dist" / "TextExpander.exe"

    if exe_src.exists():
        shutil.copy2(str(exe_src), str(out / "TextExpander.exe"))
        print(f"Copied exe: {exe_src}")
    else:
        print(f"Warning: exe not found at {exe_src}. Build it first with build_exe.bat.")

    for filename in ("shortcuts.csv", "shortcuts.txt"):
        src = find_default_shortcut_file(filename)
        if src:
            shutil.copy2(src, str(out / filename))
            print(f"Copied {filename}")

    bat = out / "Run TextExpander.bat"
    bat.write_text(
        '@echo off\ncd /d "%~dp0"\nstart "" "%~dp0TextExpander.exe" --global\n',
        encoding="utf-8",
    )
    print(f"Created launcher: {bat}")

    readme = out / "README.txt"
    readme.write_text(
        "TextExpander — portable shortcut expander\n"
        "\n"
        "1. Keep all files in the same folder.\n"
        "2. Double-click Run TextExpander.bat to start.\n"
        "3. Type a shortcut then press Space or Tab to expand.\n"
        "4. Edit shortcuts.csv and save — changes are picked up automatically.\n"
        "5. Press Ctrl+Alt+Q to quit.\n"
        "\nIf expansion doesn't work in some apps, run the bat as Administrator.\n",
        encoding="utf-8",
    )
    print(f"Created README: {readme}")
    print(f"\nShare folder ready: {out.resolve()}")


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    if args.build_share:
        build_share_folder(args.build_share)
        sys.exit(0)

    _acquire_single_instance_lock()

    csv_file = args.csv or find_default_shortcut_file("shortcuts.csv")
    text_file = args.text_file or find_default_shortcut_file("shortcuts.txt")
    shortcuts = build_shortcuts(csv_file, args.text, text_file)

    if args.global_mode:
        if csv_file and not args.csv:
            print(f"Auto-loaded CSV shortcuts from: {csv_file}")
        if text_file and not args.text_file:
            print(f"Auto-loaded text shortcuts from: {text_file}")
        run_global_expander(
            shortcuts,
            csv_file,
            args.text,
            text_file,
            args.debug_log,
        )
    else:
        text = "Please send it asap to my nj office."
        result = expand_shortcuts(text, shortcuts)
        print(result)