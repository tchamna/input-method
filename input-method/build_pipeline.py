from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def run_step(title: str, command: list[str], cwd: Path) -> None:
    print(f"\n=== {title} ===")
    print("Running:", " ".join(command))
    result = subprocess.run(command, cwd=str(cwd))
    if result.returncode != 0:
        raise RuntimeError(f"Step failed: {title}")


def main() -> int:
    project_root = Path(__file__).resolve().parent
    share_dir = project_root / "Shortcut_Expander"
    dist_exe = project_root / "dist" / "TextExpander.exe"

    python_cmd = [sys.executable]

    run_step(
        "Step 1: Install dependencies",
        python_cmd + ["-m", "pip", "install", "--upgrade", "pyinstaller", "keyboard"],
        project_root,
    )

    run_step(
        "Step 2: Build TextExpander.exe",
        python_cmd
        + [
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--onefile",
            "--name",
            "TextExpander",
            "text_expansion.py",
        ],
        project_root,
    )

    if share_dir.exists():
        shutil.rmtree(share_dir)

    if not dist_exe.exists():
        raise FileNotFoundError(f"Build output not found: {dist_exe}")

    run_step(
        "Step 3: Create Shortcut_Expander folder",
        [str(dist_exe), "--build-share", str(share_dir)],
        project_root,
    )

    required_files = [
        share_dir / "TextExpander.exe",
        share_dir / "shortcuts.csv",
        share_dir / "shortcuts.txt",
        share_dir / "Run TextExpander.bat",
        share_dir / "README.txt",
    ]

    missing = [path for path in required_files if not path.exists()]
    if missing:
        missing_text = "\n".join(str(path) for path in missing)
        raise FileNotFoundError(f"Shortcut_Expander missing files:\n{missing_text}")

    print("\nPipeline complete.")
    print(f"EXE: {dist_exe}")
    print(f"Final folder: {share_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nERROR: {exc}")
        raise SystemExit(1)
