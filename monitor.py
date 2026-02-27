# -*- coding: utf-8 -*-
"""
音频监控工具 - 使用音频峰值电平实时检测
使用 IAudioMeterInformation 替代 session.State，消除 Windows 延迟
"""

import comtypes
import time
from datetime import datetime
from pycaw.pycaw import AudioUtilities
from pycaw.pycaw import IAudioMeterInformation
from ctypes import cast, POINTER

POLL_INTERVAL = 0.2
# 峰值阈值，低于此值视为无音频（避免背景噪音误判）
PEAK_THRESHOLD = 0.001


def now():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def monitor():
    comtypes.CoInitialize()
    prev_playing: set[str] = set()

    print("=" * 55)
    print("  🎧 音频监控工具（峰值电平模式）")
    print(f"  轮询间隔: {POLL_INTERVAL}秒")
    print(f"  峰值阈值: {PEAK_THRESHOLD}")
    print("=" * 55)
    print()

    try:
        while True:
            curr_playing: set[str] = set()

            try:
                sessions = AudioUtilities.GetAllSessions()
                for session in sessions:
                    if session.Process is None:
                        continue
                    try:
                        meter = session._ctl.QueryInterface(IAudioMeterInformation)
                        peak = meter.GetPeakValue()
                        if peak > PEAK_THRESHOLD:
                            curr_playing.add(session.Process.name())
                    except Exception:
                        pass
            except Exception as e:
                print(f"[错误] {e}")
                time.sleep(1)
                continue

            # 检测变化
            started = curr_playing - prev_playing
            stopped = prev_playing - curr_playing

            for name in started:
                print(f"{now()}  正在播放：{name}")
            for name in stopped:
                print(f"{now()}  暂停播放：{name}")

            prev_playing = curr_playing
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n已退出")
    finally:
        comtypes.CoUninitialize()


if __name__ == "__main__":
    monitor()
