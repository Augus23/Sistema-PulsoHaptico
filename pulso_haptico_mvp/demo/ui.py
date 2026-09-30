import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional

import customtkinter as ctk
import tkinter as tk
from PIL import Image

from demo.config import DEMO_STEP_DURATION_SEC, VALID_POLICIES
from demo.hardware import SerialWorkerThread


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class DemoOrchestrator(threading.Thread):
    def __init__(
        self,
        worker: SerialWorkerThread,
        on_change_cb: Callable[[str, int], None],
        on_tick_cb: Callable[[int], None],
    ):
        super().__init__(daemon=True)
        self.worker = worker
        self.on_change_cb = on_change_cb
        self.on_tick_cb = on_tick_cb
        self.running = False
        self.current_policy_index = 0
        self.policy_changed_event = threading.Event()

    def start_demo(self) -> None:
        if not self.running:
            self.running = True
            self.start()

    def stop_demo(self) -> None:
        self.running = False

    def run(self) -> None:
        direction = 1
        while self.running:
            if hasattr(self.worker.ser, "target_delta"):
                current_delta = getattr(self.worker.ser, "current_delta", 0.0)
                if current_delta >= 33.5:
                    direction = -1
                elif current_delta <= 8.5:
                    direction = 1

                if direction == 1:
                    if current_delta < 9.0:
                        self.worker.ser.target_delta = 9.0 if current_delta < 2.0 else 19.0
                    elif current_delta < 19.0:
                        self.worker.ser.target_delta = 19.0
                    elif current_delta < 33.0:
                        self.worker.ser.target_delta = 33.0
                    else:
                        self.worker.ser.target_delta = 34.0
                elif current_delta > 19.0:
                    self.worker.ser.target_delta = 18.5
                elif current_delta > 9.0:
                    self.worker.ser.target_delta = 8.5
                else:
                    self.worker.ser.target_delta = 8.0
            else:
                policy = VALID_POLICIES[self.current_policy_index]
                self.worker.send_policy(policy)
                self.on_change_cb(policy, int(DEMO_STEP_DURATION_SEC))

            started_at = time.time()
            while time.time() - started_at < DEMO_STEP_DURATION_SEC:
                if not self.running:
                    return
                if self.policy_changed_event.is_set():
                    self.policy_changed_event.clear()
                    break
                remaining = int(DEMO_STEP_DURATION_SEC - (time.time() - started_at))
                self.on_tick_cb(remaining)
                time.sleep(0.2)

            self.current_policy_index = (self.current_policy_index + 1) % len(VALID_POLICIES)


class HapticDemoApp(ctk.CTk):
    def __init__(self, worker: SerialWorkerThread, is_mock: bool = False):
        super().__init__()
        self.worker = worker
        self.orchestrator: Optional[DemoOrchestrator] = None
        suffix = " (MODO SIMULADOR / MOCK)" if is_mock else ""
        self.title(f"Pulso Háptico - Panel de Control Demo{suffix}")
        self.geometry("850x780")
        self.configure(fg_color="#1a1e24")
        self.worker.on_telemetry_received = self.update_telemetry
        self.worker.on_log_message = self.append_log
        self._build_ui(is_mock)

    def _build_ui(self, is_mock: bool) -> None:
        if is_mock:
            ctk.CTkLabel(
                self,
                text="MODO MOCK: SIN ARDUINO CONECTADO",
                text_color="black",
                fg_color="#ff9800",
                font=("Roboto", 13, "bold"),
                corner_radius=8,
            ).pack(fill="x", padx=20, pady=(15, 0))

        ctk.CTkLabel(
            self,
            text="DEMO CONTROL DE POLÍTICAS HÁPTICAS",
            font=("Roboto", 22, "bold"),
            text_color="#00ADB5",
        ).pack(pady=(15, 10))

        auto_frame = ctk.CTkFrame(self, fg_color="#2a3038", corner_radius=12)
        auto_frame.pack(fill="x", padx=20, pady=5)
        self.auto_var = tk.BooleanVar(value=False)
        ctk.CTkSwitch(
            auto_frame,
            text="Modo Secuencia Automática (30s)",
            variable=self.auto_var,
            font=("Roboto", 15, "bold"),
            text_color="#EEEEEE",
            progress_color="#00ADB5",
            command=self.toggle_auto_mode,
        ).pack(side="left", padx=20, pady=15)
        self.timer_label = ctk.CTkLabel(
            auto_frame, text="Timer: --s", font=("Roboto", 15, "bold"), text_color="#00ADB5"
        )
        self.timer_label.pack(side="right", padx=20)

        button_frame = ctk.CTkFrame(
            self, fg_color="#1f242b", border_width=2, border_color="#2a3038", corner_radius=12
        )
        button_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(
            button_frame,
            text="Selección Manual de Política",
            font=("Roboto", 14, "bold"),
            text_color="#EEEEEE",
        ).pack(pady=(10, 5))
        button_container = ctk.CTkFrame(button_frame, fg_color="transparent")
        button_container.pack(fill="x", padx=15, pady=5)

        colors = {"reassure": "#2e7d32", "awareness": "#f9a825", "breath": "#1565c0", "calm_down": "#c62828"}
        hover_colors = {"reassure": "#1b5e20", "awareness": "#f57f17", "breath": "#0d47a1", "calm_down": "#b71c1c"}
        self.buttons: Dict[str, ctk.CTkButton] = {}
        for policy in VALID_POLICIES:
            button = ctk.CTkButton(
                button_container,
                text=policy.upper(),
                font=("Roboto", 14, "bold"),
                fg_color=colors[policy],
                hover_color=hover_colors[policy],
                corner_radius=8,
                command=lambda selected=policy: self.select_policy_manual(selected),
            )
            button.pack(side="left", expand=True, fill="x", padx=8)
            self.buttons[policy] = button
        ctk.CTkButton(
            button_container,
            text="STOP",
            font=("Roboto", 14, "bold"),
            fg_color="#333333",
            hover_color="#111111",
            text_color="#ff4444",
            corner_radius=8,
            width=90,
            command=self.stop_playback,
        ).pack(side="right", padx=8)

        telemetry_frame = ctk.CTkFrame(
            self, fg_color="#1f242b", border_width=2, border_color="#2a3038", corner_radius=12
        )
        telemetry_frame.pack(fill="x", padx=20, pady=5)
        self.lbl_bpm = ctk.CTkLabel(telemetry_frame, text="BPM: --", font=("Roboto", 16))
        self.lbl_smooth = ctk.CTkLabel(telemetry_frame, text="Undefined: --", font=("Roboto", 16))
        self.lbl_delta = ctk.CTkLabel(telemetry_frame, text="Undefined: --", font=("Roboto", 16))
        for column, label in enumerate((self.lbl_bpm, self.lbl_smooth, self.lbl_delta)):
            label.grid(row=0, column=column, padx=20, pady=10, sticky="ew")
        self.lbl_active_policy = ctk.CTkLabel(
            telemetry_frame,
            text="Política Activa: NINGUNA",
            font=("Roboto", 16, "bold"),
            text_color="#00ADB5",
        )
        self.lbl_active_policy.grid(row=1, column=0, columnspan=3, pady=(0, 10))
        telemetry_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.image_frame = ctk.CTkFrame(
            self, fg_color="#1f242b", border_width=2, border_color="#2a3038", corner_radius=12
        )
        self.image_frame.pack(fill="both", expand=True, padx=20, pady=(5, 20))
        self.image_label = ctk.CTkLabel(
            self.image_frame,
            text="Selecciona una política para visualizar su estado",
            font=("Roboto", 16, "italic"),
            text_color="#888888",
        )
        self.image_label.pack(expand=True, pady=10)
        self.ctk_images = self._load_policy_images()

    def _load_policy_images(self) -> Dict[str, Optional[ctk.CTkImage]]:
        names = {
            "reassure": "Demo para 189 (3).jpg",
            "awareness": "Demo para 189.jpg",
            "breath": "Demo para 189 (1).jpg",
            "calm_down": "Demo para 189 (2).jpg",
        }
        images: Dict[str, Optional[ctk.CTkImage]] = {}
        for policy, name in names.items():
            try:
                image = Image.open(Path(__file__).resolve().parent / name)
                images[policy] = ctk.CTkImage(light_image=image, dark_image=image, size=(450, 300))
            except (FileNotFoundError, OSError):
                images[policy] = None
        return images

    def update_displayed_image(self, policy: str) -> None:
        image = self.ctk_images.get(policy)
        self.image_label.configure(image=image, text="" if image else "Imagen no encontrada")

    def select_policy_manual(self, policy: str) -> None:
        if self.auto_var.get():
            self.auto_var.set(False)
            self.toggle_auto_mode()
        self.highlight_button(policy)
        self.worker.send_policy(policy)
        self.lbl_active_policy.configure(text=f"Política Activa: {policy.upper()}")
        self.update_displayed_image(policy)

    def highlight_button(self, policy: str) -> None:
        for current, button in self.buttons.items():
            button.configure(border_width=3 if current == policy else 0, border_color="#FFFFFF")

    def stop_playback(self) -> None:
        if self.auto_var.get():
            self.auto_var.set(False)
            self.toggle_auto_mode()
        self.worker.stop_motors()
        self.lbl_active_policy.configure(text="Política Activa: DETENIDO")
        self.highlight_button("")
        self.image_label.configure(image=None, text="Detenido - Sin política activa")

    def toggle_auto_mode(self) -> None:
        if self.auto_var.get():
            self.orchestrator = DemoOrchestrator(self.worker, self.on_auto_policy_change, self.on_auto_tick)
            self.orchestrator.start_demo()
        elif self.orchestrator:
            self.orchestrator.stop_demo()
            self.orchestrator = None
            self.timer_label.configure(text="Timer: --s")

    def on_auto_policy_change(self, policy: str, duration: int) -> None:
        self.after(0, lambda: self._update_auto_ui(policy))

    def _update_auto_ui(self, policy: str) -> None:
        self.highlight_button(policy)
        self.lbl_active_policy.configure(text=f"Política Activa (AUTO): {policy.upper()}")
        self.update_displayed_image(policy)

    def on_auto_tick(self, remaining: int) -> None:
        self.after(0, lambda: self.timer_label.configure(text=f"Timer: {remaining}s"))

    def update_telemetry(self, data: Dict[str, str]) -> None:
        def update() -> None:
            if data.get("signal_ok") != "1":
                return
            self.lbl_bpm.configure(text=f"BPM: {data.get('bpm', '--')}")
            if data.get("phase") == "run":
                self.lbl_smooth.configure(text=f"Baseline: {data.get('baseline_bpm', '--')}")
                self.lbl_delta.configure(text=f"Delta: {data.get('delta', '--')}")
            else:
                self.lbl_smooth.configure(text=f"Beat average: {data.get('beat_avg', '--')}")
                self.lbl_delta.configure(text=f"Samples: {data.get('baseline_samples', '--')}")

            if self.auto_var.get() and hasattr(self.worker.ser, "target_delta"):
                suggested = data.get("policy")
                current = self.lbl_active_policy.cget("text").split(": ")[-1].lower()
                if suggested in VALID_POLICIES and suggested != current:
                    self.worker.send_policy(suggested)
                    self._update_auto_ui(suggested)
                    if self.orchestrator:
                        self.orchestrator.policy_changed_event.set()

        self.after(0, update)

    def append_log(self, text: str) -> None:
        print(text)
