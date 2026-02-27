# -*- coding: utf-8 -*-
"""
Music Pause Engine - 核心引擎
===========================
音频检测 + 静音控制 + 状态机，供 Web UI 调用。
"""

import comtypes
import logging
import threading
import time
from enum import Enum, auto

from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

log = logging.getLogger("MusicPause")

# ─── 默认设置 ─────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "poll_interval": 0.2,
    "resume_delay": 1,
    "peak_threshold": 0.001,
    "browser_processes": ["chrome.exe"],
    "music_keywords": [
        "cloudmusic", "qqmusic", "spotify", "kugou", "kuwo",
        "foobar", "aimp", "musicbee", "vlc", "potplayer", "listen1",
    ],
}


class AppState(Enum):
    IDLE = auto()
    BROWSER_ACTIVE = auto()
    WAITING_RESUME = auto()


class MusicPauseEngine:
    """核心引擎：音频检测 + 静音控制 + 状态机"""

    def __init__(self, on_log=None, on_state_change=None):
        self.settings = dict(DEFAULT_SETTINGS)
        self.state = AppState.IDLE
        self._running = False
        self._resume_timer: float = 0.0
        self._muted_names: set[str] = set()
        self._prev_browser: set[str] = set()
        self._prev_music: set[str] = set()
        self._thread: threading.Thread | None = None

        # 回调
        self._on_log = on_log
        self._on_state_change = on_state_change

    @property
    def is_running(self):
        return self._running

    @property
    def status_info(self):
        return {
            "state": self.state.name,
            "running": self._running,
            "muted": list(self._muted_names),
            "browser_playing": list(self._prev_browser),
            "music_playing": list(self._prev_music),
        }

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("🎵 监控已启动")

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        # 恢复被静音的会话
        if self._muted_names:
            try:
                comtypes.CoInitialize()
                _, _, sessions = self._get_audio_state()
                self._unmute(sessions)
                comtypes.CoUninitialize()
            except Exception:
                pass
        self.state = AppState.IDLE
        self._emit_state()
        log.info("🛑 监控已停止")

    def update_settings(self, new_settings: dict):
        for key in ["poll_interval", "resume_delay", "peak_threshold"]:
            if key in new_settings:
                self.settings[key] = float(new_settings[key])
        for key in ["browser_processes", "music_keywords"]:
            if key in new_settings and isinstance(new_settings[key], list):
                self.settings[key] = [s.lower().strip() for s in new_settings[key] if s.strip()]
        log.info(f"⚙️ 设置已更新")

    @staticmethod
    def scan_audio_processes() -> list[dict]:
        """扫描系统中所有有音频会话的进程，返回进程信息列表"""
        import comtypes as _comtypes
        _comtypes.CoInitialize()
        result = {}
        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process is None:
                    continue
                name = session.Process.name().lower()
                if name in result:
                    continue
                peak = 0.0
                try:
                    meter = session._ctl.QueryInterface(IAudioMeterInformation)
                    peak = meter.GetPeakValue()
                except Exception:
                    pass
                result[name] = {
                    "name": name,
                    "playing": peak > 0.001,
                }
        except Exception as e:
            log.error(f"扫描进程出错: {e}")
        finally:
            _comtypes.CoUninitialize()
        return sorted(result.values(), key=lambda x: (not x["playing"], x["name"]))

    # ─── 内部逻辑 ──────────────────────────────────────────

    def _loop(self):
        comtypes.CoInitialize()
        try:
            while self._running:
                try:
                    self._tick()
                except Exception as e:
                    log.error(f"监控出错: {e}")
                time.sleep(self.settings["poll_interval"])
        finally:
            comtypes.CoUninitialize()

    def _get_audio_state(self):
        browser_set: set[str] = set()
        music_set: set[str] = set()
        music_sessions = []
        browser_procs = set(self.settings["browser_processes"])
        music_kws = self.settings["music_keywords"]
        threshold = self.settings["peak_threshold"]

        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process is None:
                    continue
                name = session.Process.name().lower()
                is_browser = name in browser_procs
                is_music = any(kw in name for kw in music_kws)
                if not is_browser and not is_music:
                    continue

                if is_music:
                    music_sessions.append((name, session))
                    if name in self._muted_names:
                        music_set.add(name)
                        continue

                try:
                    meter = session._ctl.QueryInterface(IAudioMeterInformation)
                    peak = meter.GetPeakValue()
                    if peak > threshold:
                        if is_browser:
                            browser_set.add(name)
                        elif is_music:
                            music_set.add(name)
                except Exception:
                    pass
        except Exception as e:
            log.error(f"检测音频时出错: {e}")

        return browser_set, music_set, music_sessions

    def _mute(self, music_sessions):
        newly_muted = set()
        for name, session in music_sessions:
            try:
                vol = session.SimpleAudioVolume
                if not vol.GetMute():
                    vol.SetMute(True, None)
                    if name not in self._muted_names and name not in newly_muted:
                        log.info(f"⏸️ 已静音: {name}")
                        newly_muted.add(name)
                    self._muted_names.add(name)
            except Exception as e:
                log.error(f"静音失败: {name}: {e}")

    def _unmute(self, music_sessions):
        for name, session in music_sessions:
            if name in self._muted_names:
                try:
                    vol = session.SimpleAudioVolume
                    vol.SetMute(False, None)
                    self._muted_names.discard(name)
                    log.info(f"▶️ 已取消静音: {name}")
                except Exception as e:
                    log.error(f"取消静音失败: {name}: {e}")

    def _emit_state(self):
        if self._on_state_change:
            self._on_state_change(self.status_info)

    def _tick(self):
        browser, music, sessions = self._get_audio_state()
        state_changed = False

        # 状态变化日志
        for n in browser - self._prev_browser:
            log.info(f"🔊 浏览器开始播放: {n}")
            state_changed = True
        for n in self._prev_browser - browser:
            log.info(f"🔇 浏览器停止播放: {n}")
            state_changed = True
        for n in music - self._prev_music:
            if n not in self._muted_names:
                log.info(f"🎵 音乐开始播放: {n}")
                state_changed = True
        for n in self._prev_music - music:
            if n not in self._muted_names:
                log.info(f"🔇 音乐停止播放: {n}")
                state_changed = True
        self._prev_browser = browser
        self._prev_music = music

        browser_on = len(browser) > 0
        music_on = len(music) > 0
        old_state = self.state

        # 状态机
        if self.state == AppState.IDLE:
            if browser_on and music_on and not self._muted_names:
                log.info(f"⏸️ 静音 {music}，浏览器正在播放 {browser}")
                self._mute(sessions)
                self.state = AppState.BROWSER_ACTIVE
            elif browser_on:
                self.state = AppState.BROWSER_ACTIVE

        elif self.state == AppState.BROWSER_ACTIVE:
            if not browser_on:
                self.state = AppState.WAITING_RESUME
                self._resume_timer = time.time()
                log.info(f"📺 浏览器停止，{self.settings['resume_delay']}秒后恢复")
            elif music_on and not self._muted_names:
                log.info(f"⏸️ 静音 {music}，浏览器正在播放 {browser}")
                self._mute(sessions)

        elif self.state == AppState.WAITING_RESUME:
            if browser_on:
                log.info("🎬 浏览器重新播放，取消恢复")
                self.state = AppState.BROWSER_ACTIVE
            elif time.time() - self._resume_timer >= self.settings["resume_delay"]:
                if self._muted_names:
                    self._unmute(sessions)
                self.state = AppState.IDLE

        if self.state != old_state or state_changed:
            self._emit_state()
