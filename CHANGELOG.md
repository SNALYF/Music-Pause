# Changelog / 更新日志

## v2.0.0 (2026-02-28)

### ✨ New Features / 新功能

- **🖥️ Native Desktop GUI** — Replaced web UI with customtkinter native window (dark theme)
- **🎧 Song Title Display** — Shows current video/music title via Windows GSMTC API
  - 🌐 Browser video title (green)
  - 🎵 Music client title (cyan, if player supports GSMTC)
- **🔊 Volume Fade Transition** — Smooth fade-out when muting, fade-in when resuming (configurable duration)
- **📋 Process Manager** — Add/remove monitored browser and music processes
  - Manual editing (one per line)
  - 🔍 Auto-detect all audio processes with one click
- **🔽 System Tray** — Minimize to tray or exit on close
- **📊 Fade Progress Bar** — Visual progress bar with ease-in-out animation for mute/unmute transitions
- **💓 Breathing Pulse** — Status indicator smoothly pulses in different colors per state
- **📝 Title in Logs** — Mute/unmute log entries include current video/music titles

### 🔧 Improvements / 改进

- **Low-latency Detection** — Uses `IAudioMeterInformation.GetPeakValue()` instead of session state
- **Session-level Mute** — Precise `SimpleAudioVolume.SetMute()` per session, no global media keys
- **Saved Volume** — Remembers original volume before muting, restores exactly on unmute

### 📦 Packaging / 打包

- Single-file EXE via PyInstaller (`dist/MusicPause.exe`)
- No Python installation required

---

## v1.0.0 (2026-02-27)

- Initial audio monitoring tool
- Basic console output for audio state detection
