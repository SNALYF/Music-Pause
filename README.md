# 🎵 Music Pause

**Auto-mute music when browser plays video**

[中文文档](README_CN.md)

## Features

- 🎬 **Auto-detect** browser (Chrome, etc.) video playback
- ⏸️ **Auto-mute** background music clients (NetEase Music, QQ Music, Spotify, etc.)
- ▶️ **Auto-unmute** when browser video stops
- 📋 **Process management** — manually add or auto-detect programs to monitor
- ⚡ **Low latency** — uses IAudioMeterInformation peak level for real-time detection
- 🔽 **System tray** — minimize to tray for background operation

## Usage

### Option 1: Run EXE (Recommended)

Download and double-click `MusicPause.exe`. No Python needed.

### Option 2: Run from Source

```bash
pip install -r requirements.txt
python app.py
```

## UI Overview

| Section | Description |
|---------|-------------|
| Status | Current state: Monitoring / Music Muted / Stopped |
| Process Cards | Real-time browser & music client status |
| Live Log | Scrolling log of all state changes |
| Settings | Poll interval, resume delay, process management |

## Build

```bash
python -m PyInstaller --onefile --windowed --name MusicPause app.py
```

Output: `dist/MusicPause.exe`

## Tech Stack

- **Python 3.10+** / **pycaw** (WASAPI) / **customtkinter** / **pystray** / **PyInstaller**
- Windows 10 / 11 required
