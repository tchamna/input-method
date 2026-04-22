# input-method

A global text expander for Windows. Type a shortcut and press Space or Tab to expand it anywhere.

## Features

- Works in any app (Chrome, Edge, Notepad, etc.)
- Auto-reloads `shortcuts.csv` while running — no restart needed
- Supports prefix expansion (e.g. `mbeu3` → `mbə̄`)
- Double-tap Shift to toggle ON/OFF
- Press Ctrl+Alt+Q to quit

## Usage

```
TextExpander.exe --global
```

Shortcuts are loaded automatically from `shortcuts.csv` in the same folder.

## shortcuts.csv format

```csv
shortcut,expansion
asap,as soon as possible
nj,New Jersey
@nj,@njsharingnetwork.org
eu3,ə̄
```

## Build the colleague share folder

Run this once after building the exe to create a ready-to-send folder:

```
.\dist\TextExpander.exe --build-share ".\Shortcut_Expander"
```

Then zip `Shortcut_Expander\` and send it. No Python required on the recipient's machine.

## Build the exe

```
build_exe.bat
```

## One-go Python orchestrator

Run one command to install deps, build exe, and create the final `Shortcut_Expander\` folder:

```
py .\build_pipeline.py
```

## Optional flags

| Flag | Description |
|---|---|
| `--global` | Run as global expander |
| `--csv PATH` | Custom CSV file (default: local `shortcuts.csv`) |
| `--text-file PATH` | Custom text shortcut file |
| `--debug-log PATH` | Write key-event debug log to file |
| `--build-share DIR` | Build shareable colleague folder |
