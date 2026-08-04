from __future__ import annotations

import json
import queue
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .audio_capture import AudioCaptureWorker, AudioDevice, list_loopback_devices

APP_TITLE = "汽车直播音频采集助手"
CONFIG_PATH = Path.home() / ".car-live-monitor-collector.json"


class CollectorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("620x460")
        self.root.minsize(560, 420)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: AudioCaptureWorker | None = None
        self.devices: list[AudioDevice] = []

        self.api_url = tk.StringVar(value="http://localhost:8000")
        self.session_id = tk.StringVar()
        self.device_name = tk.StringVar()
        self.status_text = tk.StringVar(value="等待开始")
        self.status_kind = tk.StringVar(value="idle")
        self.level = tk.DoubleVar(value=0)

        self._load_config()
        self._build_ui()
        self.refresh_devices()
        self._poll_events()

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("Subtitle.TLabel", foreground="#667085")
        style.configure("Status.TLabel", font=("Microsoft YaHei UI", 10, "bold"))

        container = ttk.Frame(self.root, padding=24)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text="采集Windows系统声音，并发送到浏览器盯播工作台。",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 20))

        form = ttk.Frame(container)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="后端地址").grid(row=0, column=0, sticky="w", pady=7)
        ttk.Entry(form, textvariable=self.api_url).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=(16, 0), pady=7
        )

        ttk.Label(form, text="场次ID").grid(row=1, column=0, sticky="w", pady=7)
        ttk.Entry(form, textvariable=self.session_id).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(16, 0), pady=7
        )

        ttk.Label(form, text="系统音频设备").grid(row=2, column=0, sticky="w", pady=7)
        self.device_combo = ttk.Combobox(
            form,
            textvariable=self.device_name,
            state="readonly",
        )
        self.device_combo.grid(row=2, column=1, sticky="ew", padx=(16, 8), pady=7)
        ttk.Button(form, text="刷新", command=self.refresh_devices).grid(
            row=2, column=2, sticky="e", pady=7
        )

        level_card = ttk.LabelFrame(container, text="实时状态", padding=16)
        level_card.pack(fill="x", pady=(20, 0))
        ttk.Label(
            level_card,
            textvariable=self.status_text,
            style="Status.TLabel",
        ).pack(anchor="w")
        self.level_bar = ttk.Progressbar(
            level_card,
            maximum=1,
            variable=self.level,
            mode="determinate",
        )
        self.level_bar.pack(fill="x", pady=(12, 4))
        ttk.Label(
            level_card,
            text="音量会随直播电脑输出变化。没有变化时请检查设备选择。",
            style="Subtitle.TLabel",
        ).pack(anchor="w")

        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=(20, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        self.start_button = ttk.Button(
            actions,
            text="开始采集",
            command=self.start_capture,
        )
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.stop_button = ttk.Button(
            actions,
            text="停止采集",
            command=self.stop_capture,
            state="disabled",
        )
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ttk.Label(
            container,
            text=(
                "提示：先在浏览器工作台创建场次并复制场次ID。"
                "正式部署时请使用HTTPS/WSS地址。"
            ),
            style="Subtitle.TLabel",
            wraplength=540,
        ).pack(anchor="w", pady=(16, 0))

    def refresh_devices(self) -> None:
        try:
            self.devices = list_loopback_devices()
            names = [device.name for device in self.devices]
            self.device_combo["values"] = names
            if names and self.device_name.get() not in names:
                self.device_name.set(names[0])
            if not names:
                self.device_name.set("")
                self.status_text.set("未发现系统音频回环设备")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"读取音频设备失败：{exc}")

    def start_capture(self) -> None:
        session_id = self.session_id.get().strip()
        api_url = self.api_url.get().strip().rstrip("/")
        selected_name = self.device_name.get()
        device = next(
            (item for item in self.devices if item.name == selected_name),
            None,
        )
        if not api_url:
            messagebox.showwarning(APP_TITLE, "请填写后端地址")
            return
        if not session_id:
            messagebox.showwarning(APP_TITLE, "请填写浏览器工作台生成的场次ID")
            return
        if not device:
            messagebox.showwarning(APP_TITLE, "请选择系统音频设备")
            return

        websocket_url = self._websocket_url(api_url, session_id)
        self.worker = AudioCaptureWorker(
            websocket_url=websocket_url,
            device_id=device.id,
            on_status=lambda kind, text: self.events.put(
                ("status", (kind, text))
            ),
            on_level=lambda level: self.events.put(("level", level)),
        )
        self.worker.start()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self._save_config()

    def stop_capture(self) -> None:
        if self.worker:
            self.worker.stop()
        self.stop_button.configure(state="disabled")

    def _poll_events(self) -> None:
        try:
            while True:
                event_type, payload = self.events.get_nowait()
                if event_type == "status":
                    kind, text = payload
                    self.status_kind.set(kind)
                    self.status_text.set(text)
                    if kind in {"error", "stopped"}:
                        self.start_button.configure(state="normal")
                        self.stop_button.configure(state="disabled")
                elif event_type == "level":
                    self.level.set(float(payload))
        except queue.Empty:
            pass
        self.root.after(75, self._poll_events)

    def on_close(self) -> None:
        if self.worker and self.worker.running:
            if not messagebox.askyesno(
                APP_TITLE,
                "正在采集音频，确定要停止并退出吗？",
            ):
                return
            self.worker.stop()
            self.worker.join()
        self._save_config()
        self.root.destroy()

    @staticmethod
    def _websocket_url(api_url: str, session_id: str) -> str:
        if api_url.startswith("https://"):
            base = "wss://" + api_url.removeprefix("https://")
        elif api_url.startswith("http://"):
            base = "ws://" + api_url.removeprefix("http://")
        else:
            base = "ws://" + api_url
        return f"{base}/ws/audio/{session_id}"

    def _load_config(self) -> None:
        if not CONFIG_PATH.exists():
            return
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            self.api_url.set(data.get("api_url", self.api_url.get()))
            self.device_name.set(data.get("device_name", ""))
        except Exception:
            return

    def _save_config(self) -> None:
        data = {
            "api_url": self.api_url.get().strip(),
            "device_name": self.device_name.get(),
        }
        CONFIG_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def main() -> None:
    root = tk.Tk()
    CollectorApp(root)
    root.mainloop()

