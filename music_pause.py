# -*- coding: utf-8 -*-
"""
Music Pause Engine - 核心引擎
===========================
音频检测 + 静音控制 + 状态机 + 歌曲信息 + 音量渐变
"""

import asyncio
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
    "fade_duration": 0.5,       # 渐变时长（秒）
    "fade_steps": 15,           # 渐变步数
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


# ─── 歌曲信息获取 ──────────────────────────────────────────

def get_media_info(browser_processes: list[str] = None, music_keywords: list[str] = None) -> list[dict] | None:
    """通过 Windows GSMTC API 获取所有媒体信息，标记来源类型"""
    if browser_processes is None:
        browser_processes = []
    if music_keywords is None:
        music_keywords = []
    browser_kws = [p.replace(".exe", "").lower() for p in browser_processes]
    music_kws = [kw.lower() for kw in music_keywords]

    try:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as SessionManager,
        )

        async def _get():
            manager = await SessionManager.request_async()
            sessions = manager.get_sessions()
            results = []
            for session in sessions:
                try:
                    app_id = (session.source_app_user_model_id or "").lower()
                    info = await session.try_get_media_properties_async()
                    title = info.title or ""
                    artist = info.artist or ""
                    if not title:
                        continue

                    # 判断类型
                    if any(kw in app_id for kw in browser_kws):
                        media_type = "browser"
                    elif any(kw in app_id for kw in music_kws):
                        media_type = "music"
                    else:
                        media_type = "other"

                    results.append({
                        "title": title,
                        "artist": artist,
                        "app": app_id,
                        "type": media_type,
                    })
                except Exception:
                    pass
            return results

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(_get())
        finally:
            loop.close()
        return results
    except Exception:
        return None


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
        self._saved_volumes: dict[str, float] = {}  # 保存静音前的音量
        self._media_info: list[dict] = []  # 当前媒体信息

        # 回调
        self._on_log = on_log
        self._on_state_change = on_state_change

    @property
    def is_running(self):
        return self._running

    @property
    def status_info(self):
        # 分类媒体信息
        browser_media = [m for m in self._media_info if m.get("type") == "browser"]
        music_media = [m for m in self._media_info if m.get("type") != "browser"]
        return {
            "state": self.state.name,
            "running": self._running,
            "muted": list(self._muted_names),
            "browser_playing": list(self._prev_browser),
            "music_playing": list(self._prev_music),
            "browser_media": browser_media,
            "music_media": music_media,
            "media_info": self._media_info,
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
                self._fade_in(sessions)
                comtypes.CoUninitialize()
            except Exception:
                pass
        self.state = AppState.IDLE
        self._emit_state()
        log.info("🛑 监控已停止")

    def update_settings(self, new_settings: dict):
        for key in ["poll_interval", "resume_delay", "peak_threshold", "fade_duration"]:
            if key in new_settings:
                self.settings[key] = float(new_settings[key])
        if "fade_steps" in new_settings:
            self.settings["fade_steps"] = int(new_settings["fade_steps"])
        for key in ["browser_processes", "music_keywords"]:
            if key in new_settings and isinstance(new_settings[key], list):
                self.settings[key] = [s.lower().strip() for s in new_settings[key] if s.strip()]
        log.info(f"⚙️ 设置已更新")

    @staticmethod
    def scan_audio_processes() -> list[dict]:
        """扫描系统中所有有音频会话的进程"""
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
                result[name] = {"name": name, "playing": peak > 0.001}
        except Exception as e:
            log.error(f"扫描进程出错: {e}")
        finally:
            _comtypes.CoUninitialize()
        return sorted(result.values(), key=lambda x: (not x["playing"], x["name"]))

    # ─── 内部逻辑 ──────────────────────────────────────────

    def _loop(self):
        comtypes.CoInitialize()
        try:
            media_counter = 0
            while self._running:
                try:
                    self._tick()
                    # 每 2 秒更新一次歌曲信息（不需要每 tick 都查）
                    media_counter += 1
                    if media_counter >= max(1, int(2.0 / self.settings["poll_interval"])):
                        media_counter = 0
                        self._update_media_info()
                except Exception as e:
                    log.error(f"监控出错: {e}")
                time.sleep(self.settings["poll_interval"])
        finally:
            comtypes.CoUninitialize()

    def _update_media_info(self):
        """更新当前播放的媒体信息"""
        info = get_media_info(self.settings["browser_processes"], self.settings["music_keywords"])
        if info is not None:
            old = self._media_info
            self._media_info = info
            if info != old:
                self._emit_state()

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

    def _fade_out(self, music_sessions):
        """渐出：音量从当前逐步降到 0，然后静音"""
        duration = self.settings["fade_duration"]
        steps = self.settings["fade_steps"]
        step_time = duration / steps
        newly_muted = set()

        # 保存原始音量并收集要处理的会话
        to_fade = []
        for name, session in music_sessions:
            if name in self._muted_names:
                continue
            try:
                vol = session.SimpleAudioVolume
                original = vol.GetMasterVolume()
                self._saved_volumes[name] = original
                to_fade.append((name, session, vol, original))
            except Exception as e:
                log.error(f"渐出准备失败: {name}: {e}")

        if not to_fade:
            return

        # 逐步降低音量
        for i in range(steps, 0, -1):
            if not self._running:
                break
            ratio = (i - 1) / steps
            for name, session, vol, original in to_fade:
                try:
                    vol.SetMasterVolume(original * ratio, None)
                except Exception:
                    pass
            time.sleep(step_time)

        # 最终静音
        for name, session, vol, original in to_fade:
            try:
                vol.SetMute(True, None)
                vol.SetMasterVolume(original, None)  # 恢复原始音量值（静音状态下）
                if name not in self._muted_names and name not in newly_muted:
                    log.info(f"⏸️ 已静音: {name}")
                    newly_muted.add(name)
                self._muted_names.add(name)
            except Exception as e:
                log.error(f"静音失败: {name}: {e}")

    def _fade_in(self, music_sessions):
        """渐入：取消静音后音量从 0 逐步恢复到原始值"""
        duration = self.settings["fade_duration"]
        steps = self.settings["fade_steps"]
        step_time = duration / steps

        to_fade = []
        for name, session in music_sessions:
            if name not in self._muted_names:
                continue
            try:
                vol = session.SimpleAudioVolume
                target = self._saved_volumes.get(name, 1.0)
                vol.SetMasterVolume(0.0, None)  # 先设音量为 0
                vol.SetMute(False, None)        # 取消静音
                to_fade.append((name, session, vol, target))
                log.info(f"▶️ 恢复中: {name}")
            except Exception as e:
                log.error(f"恢复失败: {name}: {e}")

        if not to_fade:
            return

        # 逐步提高音量
        for i in range(1, steps + 1):
            if not self._running:
                break
            ratio = i / steps
            for name, session, vol, target in to_fade:
                try:
                    vol.SetMasterVolume(target * ratio, None)
                except Exception:
                    pass
            time.sleep(step_time)

        # 确保最终音量正确
        for name, session, vol, target in to_fade:
            try:
                vol.SetMasterVolume(target, None)
            except Exception:
                pass
            self._muted_names.discard(name)
            self._saved_volumes.pop(name, None)

    def _format_now_playing(self) -> str:
        """格式化当前歌曲/视频信息用于日志"""
        parts = []
        for m in self._media_info:
            title = m.get("title", "")
            artist = m.get("artist", "")
            mtype = m.get("type", "other")
            icon = "🌐" if mtype == "browser" else "🎵"
            if title and artist:
                parts.append(f"{icon} {artist} - {title}")
            elif title:
                parts.append(f"{icon} {title}")
        if parts:
            return " | " + " / ".join(parts)
        return ""

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
                song = self._format_now_playing()
                log.info(f"⏸️ 静音 {music}，浏览器正在播放 {browser}{song}")
                self._fade_out(sessions)
                self.state = AppState.BROWSER_ACTIVE
            elif browser_on:
                self.state = AppState.BROWSER_ACTIVE

        elif self.state == AppState.BROWSER_ACTIVE:
            if not browser_on:
                self.state = AppState.WAITING_RESUME
                self._resume_timer = time.time()
                log.info(f"📺 浏览器停止，{self.settings['resume_delay']}秒后恢复")
            elif music_on and not self._muted_names:
                song = self._format_now_playing()
                log.info(f"⏸️ 静音 {music}，浏览器正在播放 {browser}{song}")
                self._fade_out(sessions)

        elif self.state == AppState.WAITING_RESUME:
            if browser_on:
                log.info("🎬 浏览器重新播放，取消恢复")
                self.state = AppState.BROWSER_ACTIVE
            elif time.time() - self._resume_timer >= self.settings["resume_delay"]:
                if self._muted_names:
                    self._fade_in(sessions)
                self.state = AppState.IDLE

        if self.state != old_state or state_changed:
            self._emit_state()
