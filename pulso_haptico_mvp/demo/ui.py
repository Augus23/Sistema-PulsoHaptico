import threading
import time
import math
from pathlib import Path
from typing import Callable, Dict, Optional

import customtkinter as ctk
import tkinter as tk
from PIL import Image

from demo.config import (
    DEMO_STEP_DURATION_SEC,
    SEQUENTIAL_POLICIES,
    SEQUENTIAL_SIMULATION,
    VALID_POLICIES,
)
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
        while self.running:
            policy = SEQUENTIAL_POLICIES[self.current_policy_index]
            if hasattr(self.worker.ser, "target_delta"):
                target_deltas = {"awareness": 12.0, "reassure": 4.0, "breath": 25.0, "calm_down": 38.0}
                self.worker.ser.target_delta = target_deltas[policy]
            else:
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

            self.current_policy_index = (self.current_policy_index + 1) % len(SEQUENTIAL_POLICIES)


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
        self.ecg_bpm = 70.0
        self.ecg_amplitude = 0.0
        self.ecg_target_bpm = 70.0
        self.ecg_target_amplitude = 0.0
        self.ecg_transition_started_at = time.monotonic()
        self.ecg_transition_from_bpm = 70.0
        self.ecg_transition_from_amplitude = 0.0
        self.ecg_signal_ok = False
        self.sequential_simulation = False
        self._build_ui(is_mock)
        self._animate_ecg()

    def _build_ui(self, is_mock: bool) -> None:
        if is_mock:
            ctk.CTkLabel(
                self,
                text="MODO MOCK: SIN ARDUINO CONECTADO",
                text_color="black",
                fg_color="#ff9800",
                font=("Roboto", 13, "bold"),
                corner_radius=8,
            ).pack(fill="x", padx=20, pady=(6, 0))

        ctk.CTkLabel(
            self,
            text="DEMO CONTROL DE POLÍTICAS HÁPTICAS",
            font=("Roboto", 22, "bold"),
            text_color="#00ADB5",
        ).pack(pady=(7, 4))

        auto_frame = ctk.CTkFrame(self, fg_color="#2a3038", corner_radius=12)
        auto_frame.pack(fill="x", padx=20, pady=3)
        self.auto_var = tk.BooleanVar(value=False)
        ctk.CTkSwitch(
            auto_frame,
            text="Modo Secuencia Automática (30s)",
            variable=self.auto_var,
            font=("Roboto", 15, "bold"),
            text_color="#EEEEEE",
            progress_color="#00ADB5",
            command=self.toggle_auto_mode,
        ).pack(side="left", padx=15, pady=8)
        self.timer_label = ctk.CTkLabel(
            auto_frame, text="Timer: --s", font=("Roboto", 14, "bold"), text_color="#00ADB5"
        )
        self.timer_label.pack(side="right", padx=15)

        button_frame = ctk.CTkFrame(
            self, fg_color="#1f242b", border_width=2, border_color="#2a3038", corner_radius=12
        )
        button_frame.pack(fill="x", padx=20, pady=3)
        ctk.CTkLabel(
            button_frame,
            text="Selección Manual de Política",
            font=("Roboto", 14, "bold"),
            text_color="#EEEEEE",
        ).pack(pady=(5, 2))
        button_container = ctk.CTkFrame(button_frame, fg_color="transparent")
        button_container.pack(fill="x", padx=12, pady=2)

        colors = {"reassure": "#2e7d32", "awareness": "#f9a825", "breath": "#1565c0", "calm_down": "#c62828"}
        hover_colors = {"reassure": "#1b5e20", "awareness": "#f57f17", "breath": "#0d47a1", "calm_down": "#b71c1c"}
        self.buttons: Dict[str, ctk.CTkButton] = {}
        for policy in VALID_POLICIES:
            button = ctk.CTkButton(
                button_container,
                text=policy.upper(),
                font=("Roboto", 13, "bold"),
                fg_color=colors[policy],
                hover_color=hover_colors[policy],
                corner_radius=8,
                command=lambda selected=policy: self.select_policy_manual(selected),
            )
            button.pack(side="left", expand=True, fill="x", padx=6)
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
        ).pack(side="right", padx=6)

        telemetry_frame = ctk.CTkFrame(
            self, fg_color="#1f242b", border_width=2, border_color="#2a3038", corner_radius=12
        )
        telemetry_frame.pack(fill="x", padx=20, pady=3)
        self.lbl_bpm = ctk.CTkLabel(telemetry_frame, text="BPM: --", font=("Roboto", 15))
        self.lbl_smooth = ctk.CTkLabel(telemetry_frame, text="Undefined: --", font=("Roboto", 15))
        self.lbl_delta = ctk.CTkLabel(telemetry_frame, text="Undefined: --", font=("Roboto", 15))
        for column, label in enumerate((self.lbl_bpm, self.lbl_smooth, self.lbl_delta)):
            label.grid(row=0, column=column, padx=12, pady=4, sticky="ew")
        self.lbl_active_policy = ctk.CTkLabel(
            telemetry_frame,
            text="Política Activa: NINGUNA",
            font=("Roboto", 15, "bold"),
            text_color="#00ADB5",
        )
        self.lbl_active_policy.grid(row=1, column=0, columnspan=3, pady=(0, 4))
        telemetry_frame.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(
            telemetry_frame,
            text="MONITOR DE PULSO",
            font=("Roboto", 12, "bold"),
            text_color="#00ADB5",
        ).grid(row=2, column=0, columnspan=3, pady=(1, 0))
        self.ecg_canvas = tk.Canvas(
            telemetry_frame,
            height=100,
            bg="#10161b",
            highlightthickness=1,
            highlightbackground="#2a3038",
        )
        self.ecg_canvas.grid(row=3, column=0, columnspan=3, padx=12, pady=(3, 7), sticky="ew")
        telemetry_frame.grid_rowconfigure(3, weight=1)

        self.image_frame = ctk.CTkFrame(
            self, fg_color="#1f242b", border_width=2, border_color="#2a3038", corner_radius=12
        )
        self.image_frame.pack(fill="both", expand=True, padx=20, pady=(3, 12))
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
            "reassure": "Demo para 189.jpg",
            "awareness": "Demo para 189 (3).jpg",
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
        self.sequential_simulation = False
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
        self.sequential_simulation = False
        self.lbl_active_policy.configure(text="Política Activa: DETENIDO")
        self.highlight_button("")
        self.image_label.configure(image=None, text="Detenido - Sin política activa")

    def toggle_auto_mode(self) -> None:
        if self.auto_var.get():
            self.sequential_simulation = True
            self.orchestrator = DemoOrchestrator(self.worker, self.on_auto_policy_change, self.on_auto_tick)
            self.orchestrator.start_demo()
        elif self.orchestrator:
            self.sequential_simulation = False
            self.orchestrator.stop_demo()
            self.orchestrator = None
            self.timer_label.configure(text="Timer: --s")

    def on_auto_policy_change(self, policy: str, duration: int) -> None:
        self.after(0, lambda: self._update_auto_ui(policy))

    def _update_auto_ui(self, policy: str) -> None:
        simulation = SEQUENTIAL_SIMULATION[policy]
        self.ecg_signal_ok = True
        self.ecg_transition_from_bpm = self.ecg_bpm
        self.ecg_transition_from_amplitude = self.ecg_amplitude
        self.ecg_target_bpm = float(simulation["bpm"])
        self.ecg_target_amplitude = float(simulation["amplitude"])
        self.ecg_transition_started_at = time.monotonic()
        self.highlight_button(policy)
        self.lbl_active_policy.configure(text=f"Política Activa (AUTO): {policy.upper()}")
        self.update_displayed_image(policy)

    def on_auto_tick(self, remaining: int) -> None:
        self.after(0, lambda: self.timer_label.configure(text=f"Timer: {remaining}s"))

    def _animate_ecg(self) -> None:
        width = max(self.ecg_canvas.winfo_width(), 400)
        height = max(self.ecg_canvas.winfo_height(), 125)
        middle = height / 2
        self.ecg_canvas.delete("wave")

        if self.sequential_simulation:
            elapsed = time.monotonic() - self.ecg_transition_started_at
            progress = min(elapsed / DEMO_STEP_DURATION_SEC, 1.0)
            self.ecg_bpm = self.ecg_transition_from_bpm + (
                self.ecg_target_bpm - self.ecg_transition_from_bpm
            ) * progress
            self.ecg_amplitude = self.ecg_transition_from_amplitude + (
                self.ecg_target_amplitude - self.ecg_transition_from_amplitude
            ) * progress
            self.lbl_bpm.configure(text=f"BPM: {round(self.ecg_bpm)}")
            self.lbl_smooth.configure(text="Simulado")
            self.lbl_delta.configure(text=f"Nivel: {round(self.ecg_amplitude)}")

        if not self.ecg_signal_ok:
            self.ecg_canvas.create_line(
                0, middle, width, middle,
                fill="#3d5960", width=2, tags="wave"
            )
            self.ecg_canvas.create_text(
                width / 2, middle - 18,
                text="Esperando una señal de pulso...",
                fill="#71858a", font=("Roboto", 11), tags="wave"
            )
        else:
            bpm = max(self.ecg_bpm, 40.0)
            period = 60.0 / bpm
            visible_seconds = 6.0
            now = time.time()
            amplitude = max(5.0, min(self.ecg_amplitude * 0.9, 38.0))
            points = []

            for x in range(0, width + 4, 4):
                sample_time = now - visible_seconds + (x / width) * visible_seconds
                beat_phase = (sample_time % period) / period
                pulse = (
                    0.14 * math.exp(-((beat_phase - 0.18) / 0.045) ** 2)
                    - 0.16 * math.exp(-((beat_phase - 0.30) / 0.018) ** 2)
                    + 1.00 * math.exp(-((beat_phase - 0.34) / 0.012) ** 2)
                    - 0.30 * math.exp(-((beat_phase - 0.38) / 0.020) ** 2)
                    + 0.28 * math.exp(-((beat_phase - 0.60) / 0.085) ** 2)
                )
                points.extend((x, middle - pulse * amplitude))

            self.ecg_canvas.create_line(
                *points,
                fill="#35e0c1",
                width=2,
                smooth=True,
                tags="wave",
            )
            self.ecg_canvas.create_line(
                0, middle, width, middle,
                fill="#23444a", width=1, tags="wave"
            )

        self.after(50, self._animate_ecg)

    def update_telemetry(self, data: Dict[str, str]) -> None:
        def update() -> None:
            if self.sequential_simulation:
                return
            self.ecg_signal_ok = data.get("signal_ok") == "1"
            if not self.ecg_signal_ok:
                self.ecg_bpm = 0.0
                self.ecg_amplitude = 0.0
                self.lbl_bpm.configure(text="BPM: 0")
                self.lbl_smooth.configure(text="Sin señal")
                self.lbl_delta.configure(text="Esperando pulso")
                return
            try:
                self.ecg_bpm = float(data.get("bpm") or data.get("beat_avg") or 70)
                self.ecg_amplitude = float(data.get("amp") or 0)
            except (TypeError, ValueError):
                self.ecg_bpm = 70.0
                self.ecg_amplitude = 0.0
            if self.ecg_bpm <= 0:
                self.ecg_signal_ok = False
                self.lbl_bpm.configure(text="BPM: 0")
                self.lbl_smooth.configure(text="Sin señal")
                self.lbl_delta.configure(text="Esperando pulso")
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
