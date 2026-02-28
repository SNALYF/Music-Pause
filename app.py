# -*- coding: utf-8 -*-
"""
Music Pause - 原生桌面应用
=========================
customtkinter GUI + pystray 系统托盘 + 动画。
"""

import customtkinter as ctk
import logging
import math
import sys
import threading
import time
from PIL import Image, ImageDraw

from music_pause import MusicPauseEngine

# ─── 日志设置 ───────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s.%(msecs)03d %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("MusicPause")


# ─── 颜色工具 ────────────────────────────────────────────

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(r, g, b):
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"

def lerp_color(c1, c2, t):
    """t=0 返回 c1, t=1 返回 c2"""
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return rgb_to_hex(r1 + (r2-r1)*t, g1 + (g2-g1)*t, b1 + (b2-b1)*t)


# ─── 主窗口 ────────────────────────────────────────────────

class MusicPauseApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # 窗口设置
        self.title("Music Pause")
        self.geometry("520x760")
        self.minsize(450, 500)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        # 引擎
        self.engine = MusicPauseEngine(on_state_change=self._on_state_change)

        # 系统托盘
        self._tray_icon = None
        self._tray_thread = None

        # 动画状态
        self._pulse_phase = 0.0
        self._prev_state = "IDLE"
        self._flash_count = 0
        self._fade_progress = 0.0  # 0.0-1.0 渐变进度
        self._fade_active = False

        # 窗口关闭处理
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 自定义日志 handler
        self._log_handler = GUILogHandler(self._append_log)
        self._log_handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(message)s", datefmt="%H:%M:%S"))
        log.addHandler(self._log_handler)

        # 构建界面
        self._build_ui()

        # 启动动画循环
        self._animate_pulse()

        # 自动启动监控
        self.after(500, self.engine.start)

    # ─── UI 构建 ──────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)  # 日志区域扩展

        # ── 标题 ──
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="ew")
        ctk.CTkLabel(title_frame, text="🎵 Music Pause",
                     font=ctk.CTkFont(size=24, weight="bold")).pack()
        ctk.CTkLabel(title_frame, text="浏览器播放视频时自动静音音乐客户端",
                     font=ctk.CTkFont(size=12), text_color="gray").pack()

        # ── 状态区域 ──
        self.status_frame = ctk.CTkFrame(self)
        self.status_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.status_frame.grid_columnconfigure(1, weight=1)

        self.status_indicator = ctk.CTkLabel(self.status_frame, text="●", font=ctk.CTkFont(size=20),
                                              text_color="#22d3ee", width=30)
        self.status_indicator.grid(row=0, column=0, padx=(15, 5), pady=12)

        status_text_frame = ctk.CTkFrame(self.status_frame, fg_color="transparent")
        status_text_frame.grid(row=0, column=1, padx=5, pady=12, sticky="w")
        self.status_label = ctk.CTkLabel(status_text_frame, text="监控中",
                                          font=ctk.CTkFont(size=15, weight="bold"))
        self.status_label.pack(anchor="w")
        self.status_sub = ctk.CTkLabel(status_text_frame, text="等待浏览器播放视频...",
                                        font=ctk.CTkFont(size=11), text_color="gray")
        self.status_sub.pack(anchor="w")

        self.toggle_btn = ctk.CTkButton(self.status_frame, text="停止", width=70, height=32,
                                         command=self._toggle_engine,
                                         fg_color="#ef4444", hover_color="#dc2626")
        self.toggle_btn.grid(row=0, column=2, padx=15, pady=12)

        # ── 进程卡片 ──
        cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        cards_frame.grid(row=2, column=0, padx=20, pady=(0, 5), sticky="ew")
        cards_frame.grid_columnconfigure(0, weight=1)
        cards_frame.grid_columnconfigure(1, weight=1)

        # 浏览器卡片
        browser_card = ctk.CTkFrame(cards_frame)
        browser_card.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        ctk.CTkLabel(browser_card, text="🌐 浏览器", font=ctk.CTkFont(size=10),
                     text_color="gray").pack(padx=12, pady=(8, 2), anchor="w")
        self.browser_label = ctk.CTkLabel(browser_card, text="● 无音频",
                                           font=ctk.CTkFont(size=13), text_color="#71717a")
        self.browser_label.pack(padx=12, pady=(2, 8), anchor="w")

        # 音乐卡片
        self.music_card = ctk.CTkFrame(cards_frame)
        self.music_card.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        ctk.CTkLabel(self.music_card, text="🎵 音乐客户端", font=ctk.CTkFont(size=10),
                     text_color="gray").pack(padx=12, pady=(8, 2), anchor="w")
        self.music_label = ctk.CTkLabel(self.music_card, text="● 无音频",
                                         font=ctk.CTkFont(size=13), text_color="#71717a")
        self.music_label.pack(padx=12, pady=(2, 8), anchor="w")

        # ── 媒体信息 ──
        self.media_frame = ctk.CTkFrame(self)
        self.media_frame.grid(row=3, column=0, padx=20, pady=(0, 5), sticky="ew")
        self.media_frame.grid_columnconfigure(1, weight=1)

        # 浏览器视频标题
        self.video_icon = ctk.CTkLabel(self.media_frame, text="🌐", font=ctk.CTkFont(size=16), width=28)
        self.video_icon.grid(row=0, column=0, padx=(12, 4), pady=(10, 2))
        self.video_title = ctk.CTkLabel(self.media_frame, text="无视频播放",
                                         font=ctk.CTkFont(size=12),
                                         text_color="#71717a", anchor="w")
        self.video_title.grid(row=0, column=1, padx=(4, 12), pady=(10, 2), sticky="w")

        # 音乐客户端标题
        self.song_icon = ctk.CTkLabel(self.media_frame, text="🎵", font=ctk.CTkFont(size=16), width=28)
        self.song_icon.grid(row=1, column=0, padx=(12, 4), pady=(2, 2))
        self.song_title = ctk.CTkLabel(self.media_frame, text="无音乐播放",
                                        font=ctk.CTkFont(size=12),
                                        text_color="#71717a", anchor="w")
        self.song_title.grid(row=1, column=1, padx=(4, 12), pady=(2, 2), sticky="w")

        # 渐变进度条
        self.fade_bar = ctk.CTkProgressBar(self.media_frame, height=3, width=200,
                                            progress_color="#22d3ee")
        self.fade_bar.grid(row=2, column=0, columnspan=2, padx=12, pady=(2, 8), sticky="ew")
        self.fade_bar.set(0)

        # ── 日志区域 ──
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=4, column=0, padx=20, pady=5, sticky="nsew")
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.grid(row=0, column=0, padx=12, pady=(8, 0), sticky="ew")
        log_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_header, text="📋 实时日志", font=ctk.CTkFont(size=11),
                     text_color="gray").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(log_header, text="清除", width=50, height=24,
                      font=ctk.CTkFont(size=11), fg_color="transparent",
                      border_width=1, border_color="gray",
                      command=self._clear_log).grid(row=0, column=1)

        self.log_text = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(family="Consolas", size=12),
                                        state="disabled", wrap="none",
                                        fg_color="transparent", height=200)
        self.log_text.grid(row=1, column=0, padx=8, pady=(4, 8), sticky="nsew")

        # ── 设置区域 ──
        settings_frame = ctk.CTkFrame(self)
        settings_frame.grid(row=5, column=0, padx=20, pady=(5, 20), sticky="ew")
        settings_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(settings_frame, text="⚙️ 设置", font=ctk.CTkFont(size=11),
                     text_color="gray").grid(row=0, column=0, columnspan=3, padx=12, pady=(8, 4), sticky="w")

        # 轮询间隔
        ctk.CTkLabel(settings_frame, text="轮询间隔", font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, padx=(12, 5), pady=4, sticky="w")
        self.poll_slider = ctk.CTkSlider(settings_frame, from_=0.1, to=2.0,
                                          number_of_steps=19, command=self._on_poll_change)
        self.poll_slider.set(0.2)
        self.poll_slider.grid(row=1, column=1, padx=5, pady=4, sticky="ew")
        self.poll_val = ctk.CTkLabel(settings_frame, text="0.2s", font=ctk.CTkFont(size=12),
                                      text_color="#22d3ee", width=40)
        self.poll_val.grid(row=1, column=2, padx=(5, 12), pady=4)

        # 恢复延迟
        ctk.CTkLabel(settings_frame, text="恢复延迟", font=ctk.CTkFont(size=12)).grid(
            row=2, column=0, padx=(12, 5), pady=(4, 8), sticky="w")
        self.delay_slider = ctk.CTkSlider(settings_frame, from_=0, to=10,
                                           number_of_steps=20, command=self._on_delay_change)
        self.delay_slider.set(1)
        self.delay_slider.grid(row=2, column=1, padx=5, pady=(4, 8), sticky="ew")
        self.delay_val = ctk.CTkLabel(settings_frame, text="1s", font=ctk.CTkFont(size=12),
                                       text_color="#22d3ee", width=40)
        self.delay_val.grid(row=2, column=2, padx=(5, 12), pady=(4, 4))

        # 管理进程按钮
        ctk.CTkButton(settings_frame, text="📋 管理监控进程", height=32,
                      font=ctk.CTkFont(size=12),
                      fg_color="transparent", border_width=1, border_color="gray",
                      hover_color="#333333",
                      command=self._open_process_manager).grid(
            row=3, column=0, columnspan=3, padx=12, pady=(4, 10), sticky="ew")

    # ─── 回调 ─────────────────────────────────────────────

    def _on_state_change(self, info):
        """引擎状态变化回调（从后台线程调用）"""
        self.after(0, lambda: self._update_ui(info))

    def _update_ui(self, info):
        """更新 UI（主线程）"""
        state = info.get("state", "IDLE")
        running = info.get("running", False)
        muted = info.get("muted", [])
        browsers = info.get("browser_playing", [])
        music = info.get("music_playing", [])

        old_state = self._prev_state
        self._prev_state = state

        # 状态指示
        if not running:
            self.status_label.configure(text="已停止")
            self.status_sub.configure(text="监控未运行")
            self.toggle_btn.configure(text="启动", fg_color="#22d3ee", hover_color="#06b6d4")
        elif state in ("BROWSER_ACTIVE", "WAITING_RESUME") and muted:
            self.status_label.configure(text="音乐已静音")
            self.status_sub.configure(text=f"已静音: {', '.join(muted)}")
            self.toggle_btn.configure(text="停止", fg_color="#ef4444", hover_color="#dc2626")
        else:
            self.status_label.configure(text="监控中")
            self.status_sub.configure(text="等待浏览器播放视频...")
            self.toggle_btn.configure(text="停止", fg_color="#ef4444", hover_color="#dc2626")

        # 状态变化 → 进度条动画
        if state != old_state:
            if state in ("BROWSER_ACTIVE", "WAITING_RESUME") and muted:
                self.fade_bar.configure(progress_color="#fb923c")
                self._animate_fade_bar(1.0, 0.0)  # 渐出动画
            elif old_state in ("BROWSER_ACTIVE", "WAITING_RESUME") and state == "IDLE":
                self.fade_bar.configure(progress_color="#4ade80")
                self._animate_fade_bar(0.0, 1.0)  # 渐入动画

        # 进程卡片
        if browsers:
            self.browser_label.configure(text=f"● {', '.join(browsers)}", text_color="#4ade80")
        else:
            self.browser_label.configure(text="● 无音频", text_color="#71717a")

        if muted:
            self.music_label.configure(text=f"● {', '.join(muted)} (已静音)", text_color="#fb923c")
        elif music:
            self.music_label.configure(text=f"● {', '.join(music)}", text_color="#4ade80")
        else:
            self.music_label.configure(text="● 无音频", text_color="#71717a")

        # 媒体标题
        browser_media = info.get("browser_media", [])
        music_media = info.get("music_media", [])

        if browser_media:
            vm = browser_media[0]
            t = vm.get("title", "")
            self.video_title.configure(text=t, text_color="#4ade80")
        else:
            self.video_title.configure(text="无视频播放", text_color="#71717a")

        if music_media:
            sm = music_media[0]
            title = sm.get("title", "")
            artist = sm.get("artist", "")
            text = f"{artist} - {title}" if artist else title
            self.song_title.configure(text=text, text_color="#22d3ee")
        else:
            self.song_title.configure(text="无音乐播放", text_color="#71717a")

    def _append_log(self, msg):
        """添加日志（可能从后台线程调用）"""
        self.after(0, lambda: self._add_log_line(msg))

    def _add_log_line(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 500:
            self.log_text.delete("1.0", f"{lines - 500}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ─── 动画方法 ───────────────────────────────────────

    def _animate_pulse(self):
        """状态指示器呼吸脉冲动画"""
        self._pulse_phase += 0.08
        t = (math.sin(self._pulse_phase) + 1) / 2

        state = self._prev_state
        if not self.engine.is_running:
            color = lerp_color("#3f3f46", "#71717a", t)
        elif state in ("BROWSER_ACTIVE", "WAITING_RESUME") and self.engine._muted_names:
            color = lerp_color("#7c2d12", "#fb923c", t)
        else:
            color = lerp_color("#0e4d5c", "#22d3ee", t)

        self.status_indicator.configure(text_color=color)
        self.after(50, self._animate_pulse)

    def _animate_fade_bar(self, start, end):
        """渐变进度条动画"""
        steps = 30
        duration = 800
        step_ms = duration // steps
        self._fade_step = 0
        self._fade_start = start
        self._fade_end = end
        self._fade_steps = steps
        self._fade_step_ms = step_ms
        self._do_fade_bar()

    def _do_fade_bar(self):
        if self._fade_step > self._fade_steps:
            return
        t = self._fade_step / self._fade_steps
        # 缓动函数 (ease-in-out)
        t = t * t * (3 - 2 * t)
        val = self._fade_start + (self._fade_end - self._fade_start) * t
        self.fade_bar.set(max(0, min(1, val)))
        self._fade_step += 1
        self.after(self._fade_step_ms, self._do_fade_bar)

    def _toggle_engine(self):
        if self.engine.is_running:
            self.engine.stop()
        else:
            self.engine.start()

    def _on_poll_change(self, val):
        val = round(val, 1)
        self.poll_val.configure(text=f"{val}s")
        self.engine.update_settings({"poll_interval": val})

    def _on_delay_change(self, val):
        val = round(val, 1)
        self.delay_val.configure(text=f"{val}s")
        self.engine.update_settings({"resume_delay": val})

    def _open_process_manager(self):
        """打开进程管理对话框"""
        dialog = ProcessManagerDialog(self, self.engine)
        self.wait_window(dialog)

    # ─── 关闭/托盘 ────────────────────────────────────────

    def _on_close(self):
        """关闭窗口时弹出选项"""
        dialog = CloseDialog(self)
        self.wait_window(dialog)
        choice = dialog.result

        if choice == "tray":
            self._minimize_to_tray()
        elif choice == "exit":
            self._quit_app()

    def _minimize_to_tray(self):
        """最小化到系统托盘"""
        self.withdraw()  # 隐藏窗口

        if self._tray_icon is None:
            import pystray
            from pystray import MenuItem as Item

            icon_img = self._create_tray_icon_image()
            menu = pystray.Menu(
                Item("显示窗口", self._show_from_tray),
                pystray.Menu.SEPARATOR,
                Item("退出", self._quit_from_tray),
            )
            self._tray_icon = pystray.Icon("MusicPause", icon_img, "Music Pause", menu)
            self._tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True)
            self._tray_thread.start()

    def _show_from_tray(self, icon=None, item=None):
        """从托盘恢复窗口"""
        self.after(0, self.deiconify)

    def _quit_from_tray(self, icon=None, item=None):
        """从托盘退出"""
        if self._tray_icon:
            self._tray_icon.stop()
        self.after(0, self._quit_app)

    def _quit_app(self):
        """完全退出"""
        self.engine.stop()
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        self.destroy()
        sys.exit(0)

    @staticmethod
    def _create_tray_icon_image():
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, size - 4, size - 4], fill="#4FC3F7")
        bw, bh, gap = 8, 28, 6
        cx, cy = size // 2, size // 2
        x1, y1 = cx - gap // 2 - bw, cy - bh // 2
        draw.rectangle([x1, y1, x1 + bw, y1 + bh], fill="white")
        x2 = cx + gap // 2
        draw.rectangle([x2, y1, x2 + bw, y1 + bh], fill="white")
        return img


# ─── 进程管理对话框 ────────────────────────────────────────

class ProcessManagerDialog(ctk.CTkToplevel):
    def __init__(self, parent, engine: MusicPauseEngine):
        super().__init__(parent)
        self.engine = engine
        self.title("管理监控进程")
        self.geometry("500x520")
        self.resizable(True, True)
        self.minsize(400, 400)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 500) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 520) // 2
        self.geometry(f"+{x}+{y}")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # ── 浏览器进程 ──
        ctk.CTkLabel(self, text="🌐 浏览器进程", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, padx=16, pady=(16, 4), sticky="w")

        browser_frame = ctk.CTkFrame(self)
        browser_frame.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="nsew")
        browser_frame.grid_columnconfigure(0, weight=1)
        browser_frame.grid_rowconfigure(0, weight=1)

        self.browser_list = ctk.CTkTextbox(browser_frame, height=100, font=ctk.CTkFont(family="Consolas", size=12))
        self.browser_list.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="nsew")
        self.browser_list.insert("1.0", "\n".join(engine.settings["browser_processes"]))

        ctk.CTkLabel(browser_frame, text="每行一个进程名，如 chrome.exe",
                     font=ctk.CTkFont(size=10), text_color="gray").grid(
            row=1, column=0, padx=8, pady=(0, 8), sticky="w")

        # ── 音乐客户端关键词 ──
        ctk.CTkLabel(self, text="🎵 音乐客户端关键词", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=2, column=0, padx=16, pady=(8, 4), sticky="w")

        music_frame = ctk.CTkFrame(self)
        music_frame.grid(row=3, column=0, padx=16, pady=(0, 8), sticky="nsew")
        music_frame.grid_columnconfigure(0, weight=1)
        music_frame.grid_rowconfigure(0, weight=1)

        self.music_list = ctk.CTkTextbox(music_frame, height=100, font=ctk.CTkFont(family="Consolas", size=12))
        self.music_list.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="nsew")
        self.music_list.insert("1.0", "\n".join(engine.settings["music_keywords"]))

        ctk.CTkLabel(music_frame, text="每行一个关键词，进程名包含该词即匹配",
                     font=ctk.CTkFont(size=10), text_color="gray").grid(
            row=1, column=0, padx=8, pady=(0, 8), sticky="w")

        # ── 按钮区 ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=4, column=0, padx=16, pady=(4, 16), sticky="ew")

        ctk.CTkButton(btn_frame, text="🔍 自动检测", width=120, height=34,
                      fg_color="#6366f1", hover_color="#4f46e5",
                      command=self._auto_detect).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_frame, text="保存", width=100, height=34,
                      fg_color="#22d3ee", hover_color="#06b6d4",
                      command=self._save).pack(side="right", padx=(8, 0))

        ctk.CTkButton(btn_frame, text="取消", width=100, height=34,
                      fg_color="transparent", border_width=1, border_color="gray",
                      command=self.destroy).pack(side="right")

    def _save(self):
        browsers = [s.strip().lower() for s in self.browser_list.get("1.0", "end").split("\n") if s.strip()]
        keywords = [s.strip().lower() for s in self.music_list.get("1.0", "end").split("\n") if s.strip()]
        self.engine.update_settings({"browser_processes": browsers, "music_keywords": keywords})
        self.destroy()

    def _auto_detect(self):
        """扫描所有音频进程，弹出选择对话框"""
        detect_dialog = AutoDetectDialog(self, self.engine)
        self.wait_window(detect_dialog)
        if detect_dialog.selected_browsers or detect_dialog.selected_music:
            # 追加到列表
            if detect_dialog.selected_browsers:
                current = self.browser_list.get("1.0", "end").strip()
                for name in detect_dialog.selected_browsers:
                    if name not in current:
                        self.browser_list.insert("end", ("\n" if current else "") + name)
                        current += "\n" + name
            if detect_dialog.selected_music:
                current = self.music_list.get("1.0", "end").strip()
                for name in detect_dialog.selected_music:
                    kw = name.replace(".exe", "")
                    if kw not in current:
                        self.music_list.insert("end", ("\n" if current else "") + kw)
                        current += "\n" + kw


# ─── 自动检测对话框 ────────────────────────────────────────

class AutoDetectDialog(ctk.CTkToplevel):
    def __init__(self, parent, engine: MusicPauseEngine):
        super().__init__(parent)
        self.title("自动检测音频进程")
        self.geometry("420x450")
        self.resizable(False, True)
        self.transient(parent)
        self.grab_set()
        self.selected_browsers: list[str] = []
        self.selected_music: list[str] = []

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 420) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 450) // 2
        self.geometry(f"+{x}+{y}")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="检测到的音频进程",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, padx=16, pady=(16, 4), sticky="w")

        # 进程列表（滚动）
        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.grid(row=1, column=0, padx=16, pady=8, sticky="nsew")
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        # 扫描
        self._checkboxes: list[tuple[ctk.CTkCheckBox, str, ctk.CTkOptionMenu]] = []
        self._scan(engine)

        # 按钮
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=16, pady=(4, 16), sticky="ew")

        ctk.CTkButton(btn_frame, text="🔄 刷新", width=80, height=32,
                      fg_color="#6366f1", hover_color="#4f46e5",
                      command=lambda: self._scan(engine)).pack(side="left")

        ctk.CTkButton(btn_frame, text="添加选中", width=100, height=32,
                      fg_color="#22d3ee", hover_color="#06b6d4",
                      command=self._confirm).pack(side="right", padx=(8, 0))

        ctk.CTkButton(btn_frame, text="取消", width=80, height=32,
                      fg_color="transparent", border_width=1, border_color="gray",
                      command=self.destroy).pack(side="right")

    def _scan(self, engine):
        # 清空旧内容
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self._checkboxes.clear()

        # 在后台扫描
        processes = MusicPauseEngine.scan_audio_processes()

        if not processes:
            ctk.CTkLabel(self.scroll_frame, text="未检测到任何音频进程",
                         text_color="gray").pack(pady=20)
            return

        for proc in processes:
            name = proc["name"]
            playing = proc["playing"]

            row_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=2)
            row_frame.grid_columnconfigure(1, weight=1)

            cb_var = ctk.StringVar(value="off")
            cb = ctk.CTkCheckBox(row_frame, text="", variable=cb_var,
                                 onvalue="on", offvalue="off", width=24)
            cb.grid(row=0, column=0, padx=(4, 0))

            status_dot = "🟢" if playing else "⚫"
            label_text = f"{status_dot} {name}"
            ctk.CTkLabel(row_frame, text=label_text, font=ctk.CTkFont(size=12),
                         anchor="w").grid(row=0, column=1, padx=4, sticky="w")

            role = ctk.CTkOptionMenu(row_frame, values=["浏览器", "音乐客户端"],
                                     width=100, height=26, font=ctk.CTkFont(size=11))
            role.set("音乐客户端")
            role.grid(row=0, column=2, padx=4)

            self._checkboxes.append((cb, name, role))

    def _confirm(self):
        for cb, name, role in self._checkboxes:
            if cb.get() == "on":
                if role.get() == "浏览器":
                    self.selected_browsers.append(name)
                else:
                    self.selected_music.append(name)
        self.destroy()


# ─── 关闭对话框 ────────────────────────────────────────────

class CloseDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self.title("关闭")
        self.geometry("320x160")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 320) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 160) // 2
        self.geometry(f"+{x}+{y}")

        ctk.CTkLabel(self, text="选择关闭方式", font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(20, 15))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=5)

        ctk.CTkButton(btn_frame, text="最小化到托盘", width=130, height=36,
                      fg_color="#22d3ee", hover_color="#06b6d4",
                      command=lambda: self._choose("tray")).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="退出程序", width=130, height=36,
                      fg_color="#ef4444", hover_color="#dc2626",
                      command=lambda: self._choose("exit")).pack(side="left", padx=8)

    def _choose(self, choice):
        self.result = choice
        self.destroy()


# ─── 日志 Handler ──────────────────────────────────────────

class GUILogHandler(logging.Handler):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def emit(self, record):
        try:
            msg = self.format(record)
            self._callback(msg)
        except Exception:
            pass


# ─── 入口 ──────────────────────────────────────────────────

if __name__ == "__main__":
    app = MusicPauseApp()
    app.mainloop()
