# 🎵 Music Pause

**浏览器播放视频时自动静音音乐客户端**

[English](README.md)

## 功能

- 🎬 **自动检测**浏览器（Chrome 等）播放视频
- ⏸️ **自动静音**后台音乐客户端（网易云音乐、QQ音乐、Spotify 等）
- ▶️ 浏览器视频停止后**自动恢复**音乐
- 📋 **进程管理** — 手动添加或自动检测要监控的程序
- ⚡ **低延迟** — 使用 IAudioMeterInformation 峰值电平实时检测
- 🔽 支持**最小化到系统托盘**后台运行

## 使用方法

### 方式一：直接运行 EXE（推荐）

下载并双击 `MusicPause.exe` 即可启动，无需安装 Python。

### 方式二：从源码运行

```bash
pip install -r requirements.txt
python app.py
```

## 界面说明

| 区域 | 功能 |
|------|------|
| 状态区 | 当前监控状态（监控中 / 音乐已静音 / 已停止） |
| 进程卡片 | 实时显示浏览器和音乐客户端状态 |
| 实时日志 | 滚动显示所有状态变化 |
| 设置 | 轮询间隔、恢复延迟、管理监控进程 |

## 自行打包

```bash
python -m PyInstaller --onefile --windowed --name MusicPause app.py
```

生成 `dist/MusicPause.exe`。

## 技术栈

- **Python 3.10+** / **pycaw** (WASAPI) / **customtkinter** / **pystray** / **PyInstaller**
- 需要 Windows 10 / 11
