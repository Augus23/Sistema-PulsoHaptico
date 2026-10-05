import argparse
import threading
import time
import math
import sys
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
from demo.hardware import MockArduinoSerial, SerialWorkerThread
from demo.protocol import load_catalog


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# =============================================================================
# ORQUESTADOR MODO AUTOMÁTICO (LÓGICA CORE)
# =============================================================================
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
        self.fake_delta = 0.0
        self.target_delta = 9.0
        self.delta_step_value = 0.0

    def start_demo(self) -> None:
        if not self.running:
            self.running = True
            super().__init__(daemon=True)
            self.start()

    def stop_demo(self) -> None:
        self.running = False
        self.policy_changed_event.set()

    def run(self) -> None:
        direction = 1  # 1 = subiendo, -1 = bajando
        self.fake_delta = 0.0
        
        while self.running:
            current_d = self.fake_delta
            
            # Máquina de estados para subir y bajar lentamente
            if current_d >= 33.09:
                direction = -1
            elif current_d <= 8.91:
                direction = 1

            if direction == 1:
                if current_d < 5.0:
                    self.target_delta = 9.05
                elif current_d < 14.0:
                    self.target_delta = 19.05
                elif current_d < 26.0:
                    self.target_delta = 33.05
                else:
                    self.target_delta = 33.1
            else:
                if current_d > 26.0:
                    self.target_delta = 18.95
                elif current_d > 14.0:
                    self.target_delta = 8.95
                else:
                    self.target_delta = 8.9

            transition_time = max(1.0, float(DEMO_STEP_DURATION_SEC))
            self.delta_step_value = abs(self.target_delta - self.fake_delta) / transition_time

            start_time = time.time()
            last_tick = start_time
            while time.time() - start_time < DEMO_STEP_DURATION_SEC:
                if not self.running:
                    return
                if self.policy_changed_event.is_set():
                    self.policy_changed_event.clear()
                    break
                
                now = time.time()
                dt = now - last_tick
                last_tick = now
                
                if self.fake_delta < self.target_delta:
                    self.fake_delta = min(self.target_delta, self.fake_delta + self.delta_step_value * dt)
                elif self.fake_delta > self.target_delta:
                    self.fake_delta = max(self.target_delta, self.fake_delta - self.delta_step_value * dt)

                remaining = int(math.ceil(DEMO_STEP_DURATION_SEC - (now - start_time)))
                self.on_tick_cb(remaining)
                time.sleep(0.1)


# =============================================================================
# MÓDULO DE INTERFAZ GRÁFICA (VISTA)
# =============================================================================
class HapticUIView:
    """
    Clase responsable exclusivamente de la inicialización, manipulación visual,
    imágenes, animaciones de canvas y actualización gráfica (CustomTkinter).
    """
    MOCK_ECG_POLICY_LEVELS = {
        "awareness": (8.0, "AWARENESS - NIVEL 1"),
        "reassure": (14.0, "REASSURE - NIVEL 2"),
        "breath": (22.0, "BREATH - NIVEL 3"),
        "calm_down": (31.0, "CALM DOWN - NIVEL 4"),
    }
    POLICY_SCENARIOS = {
        "awareness": (
            "Un cambio de actividad",
            "En una transicion cotidiana se acumulan ruido, movimiento o conversaciones. Puede ser un momento para notar las primeras señales de incomodidad.",
            "Una señal suave acompana la atencion al pulso.",
        ),
        "reassure": (
            "Un plan que cambia",
            "Una modificacion inesperada de la rutina puede generar incertidumbre o tension.",
            "Un ritmo predecible ofrece una referencia estable.",
        ),
        "breath": (
            "Un entorno muy estimulante",
            "En un lugar concurrido, el ruido y la actividad pueden hacer que la activacion siga subiendo.",
            "El patron ritmico acompaña una pausa y una respiracion mas lenta.",
        ),
        "calm_down": (
            "Necesidad de bajar estimulos",
            "Tras acumularse varios estimulos, puede ayudar hacer una pausa o buscar un lugar mas tranquilo.",
            "La secuencia acompaña la autorregulacion, respetando lo que le resulte comodo a la persona.",
        ),
    }

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
            text=f"Modo Secuencia Automática ({DEMO_STEP_DURATION_SEC})",
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
        self.image_frame.grid_columnconfigure(0, weight=3)
        self.image_frame.grid_columnconfigure(1, weight=2)
        self.image_frame.grid_rowconfigure(2, weight=1)
        self.image_label = ctk.CTkLabel(
            self.image_frame,
            text="Selecciona una política para visualizar su estado",
            font=("Roboto", 13, "italic"),
            text_color="#888888",
        )
        self.image_label.grid(row=0, column=0, rowspan=5, padx=(12, 10), pady=12, sticky="nsew")
        self.image_placeholder_label = ctk.CTkLabel(
            self.image_frame,
            text="Selecciona una política para visualizar su estado",
            font=("Roboto", 13, "italic"),
            text_color="#888888",
            justify="center",
            wraplength=300,
        )
        self.image_placeholder_label.grid(
            row=0, column=0, rowspan=5, padx=(20, 18), pady=12, sticky="nsew"
        )
        self.scenario_level_label = ctk.CTkLabel(
            self.image_frame,
            text="SIN POLITICA ACTIVA",
            font=("Roboto", 11, "bold"),
            text_color="#00ADB5",
            anchor="w",
        )
        self.scenario_level_label.grid(row=0, column=1, padx=(8, 16), pady=(18, 2), sticky="ew")
        self.scenario_title_label = ctk.CTkLabel(
            self.image_frame,
            text="Escenas cotidianas",
            font=("Roboto", 18, "bold"),
            text_color="#EEEEEE",
            anchor="w",
            justify="left",
            wraplength=270,
        )
        self.scenario_title_label.grid(row=1, column=1, padx=(8, 16), pady=(0, 8), sticky="ew")
        self.scenario_description_label = ctk.CTkLabel(
            self.image_frame,
            text="Selecciona una politica para ver una situacion posible asociada a ella.",
            font=("Roboto", 13),
            text_color="#D2D8D6",
            anchor="nw",
            justify="left",
            wraplength=270,
        )
        self.scenario_description_label.grid(row=2, column=1, padx=(8, 16), pady=(0, 12), sticky="new")
        self.scenario_support_label = ctk.CTkLabel(
            self.image_frame,
            text="ACOMPAÑAMIENTO HAPTICO",
            font=("Roboto", 11, "bold"),
            text_color="#9FC7B7",
            anchor="w",
        )
        self.scenario_support_label.grid(row=3, column=1, padx=(8, 16), pady=(4, 2), sticky="ew")
        self.scenario_response_label = ctk.CTkLabel(
            self.image_frame,
            text="",
            font=("Roboto", 13),
            text_color="#D2D8D6",
            anchor="nw",
            justify="left",
            wraplength=270,
        )
        self.scenario_response_label.grid(row=4, column=1, padx=(8, 16), pady=(0, 10), sticky="new")
        self.scenario_note_label = ctk.CTkLabel(
            self.image_frame,
            text="Ejemplos ilustrativos; cada persona vive los estimulos de manera distinta.",
            font=("Roboto", 10, "italic"),
            text_color="#899895",
            anchor="w",
            justify="left",
            wraplength=270,
        )
        self.scenario_note_label.grid(row=5, column=1, padx=(8, 16), pady=(0, 16), sticky="ew")
        self.ctk_images = self._load_policy_images()
        self.update_displayed_image(None)

    def _load_policy_images(self) -> Dict[str, Optional[ctk.CTkImage]]:
        names = {
            "awareness": "static/awareness.jpg",
            "reassure": "static/reassure.jpg",
            "breath": "static/breath.jpg",
            "calm_down": "static/calm_down.jpg",
        }
        images: Dict[str, Optional[ctk.CTkImage]] = {}
        for policy, name in names.items():
            try:
                image = Image.open(Path(__file__).resolve().parent / name)
                images[policy] = ctk.CTkImage(light_image=image, dark_image=image, size=(450, 300))
            except (FileNotFoundError, OSError):
                images[policy] = None
        return images

    def update_displayed_image(self, policy: Optional[str]) -> None:
        if policy not in self.POLICY_SCENARIOS:
            self.image_label.grid_remove()
            self.image_placeholder_label.grid()
            self.scenario_level_label.configure(text="SIN POLITICA ACTIVA")
            self.scenario_title_label.configure(text="Escenas cotidianas")
            self.scenario_description_label.configure(
                text="Selecciona una politica para ver una situacion posible asociada a ella."
            )
            self.scenario_support_label.configure(text="ACOMPANAMIENTO HAPTICO")
            self.scenario_response_label.configure(text="")
            return

        self.image_placeholder_label.grid_remove()
        self.image_label.grid()
        image = self.ctk_images.get(policy)
        self.image_label.configure(image=image, text="" if image else "Imagen no encontrada")
        title, description, response = self.POLICY_SCENARIOS[policy]
        _, level_label = self.MOCK_ECG_POLICY_LEVELS[policy]
        self.scenario_level_label.configure(text=level_label)
        self.scenario_title_label.configure(text=title)
        self.scenario_description_label.configure(text=description)
        self.scenario_support_label.configure(text="ACOMPANAMIENTO HAPTICO")
        self.scenario_response_label.configure(text=response)

    def highlight_button(self, policy: str) -> None:
        for current, button in self.buttons.items():
            button.configure(border_width=3 if current == policy else 0, border_color="#FFFFFF")

    def _animate_ecg(self) -> None:
        width = max(self.ecg_canvas.winfo_width(), 400)
        height = max(self.ecg_canvas.winfo_height(), 125)
        middle = height / 2
        self.ecg_canvas.delete("wave")
        use_mock_visuals = self.is_mock or self.auto_var.get()

        if self.sequential_simulation:
            elapsed = time.monotonic() - self.ecg_transition_started_at
            progress = min(elapsed / DEMO_STEP_DURATION_SEC, 1.0)
            self.ecg_bpm = self.ecg_transition_from_bpm + (
                self.ecg_target_bpm - self.ecg_transition_from_bpm
            ) * progress
            self.ecg_amplitude = self.ecg_transition_from_amplitude + (
                self.ecg_target_amplitude - self.ecg_transition_from_amplitude
            ) * progress

        if not self.ecg_signal_ok or (use_mock_visuals and self.ecg_policy is None):
            waiting_text = (
                "Sin pulso - selecciona una política"
                if use_mock_visuals and self.ecg_policy is None
                else "Esperando una señal de pulso..."
            )
            self.ecg_canvas.create_line(
                0, middle, width, middle,
                fill="#3d5960", width=2, tags="wave"
            )
            self.ecg_canvas.create_text(
                width / 2, middle - 18,
                text=waiting_text,
                fill="#71858a", font=("Roboto", 11), tags="wave"
            )
        else:
            bpm = max(self.ecg_bpm, 40.0)
            period = 60.0 / bpm
            visible_seconds = 6.0
            now = time.time()
            if use_mock_visuals:
                amplitude, policy_label = self.MOCK_ECG_POLICY_LEVELS.get(
                    self.ecg_policy, self.MOCK_ECG_POLICY_LEVELS["reassure"]
                )
            else:
                amplitude = max(5.0, min(self.ecg_amplitude * 0.9, 38.0))
            points = []

            if use_mock_visuals:
                for division in range(1, 12):
                    x = width * division / 12
                    color = "#26373a" if division % 3 == 0 else "#1c2a2d"
                    self.ecg_canvas.create_line(x, 0, x, height, fill=color, width=1, tags="wave")
                for division in range(1, 4):
                    y = height * division / 4
                    color = "#26373a" if division == 2 else "#1c2a2d"
                    self.ecg_canvas.create_line(0, y, width, y, fill=color, width=1, tags="wave")
                self.ecg_canvas.create_text(
                    width - 10,
                    11,
                    text=policy_label,
                    anchor="ne",
                    fill="#9bb7a8",
                    font=("Roboto", 9, "bold"),
                    tags="wave",
                )

            for x in range(0, width + 4, 4):
                sample_time = now - visible_seconds + (x / width) * visible_seconds
                beat_phase = (sample_time % period) / period
                if use_mock_visuals:
                    pulse = (
                        0.12 * math.exp(-((beat_phase - 0.18) / 0.05) ** 2)
                        - 0.12 * math.exp(-((beat_phase - 0.29) / 0.025) ** 2)
                        + 0.78 * math.exp(-((beat_phase - 0.33) / 0.022) ** 2)
                        - 0.20 * math.exp(-((beat_phase - 0.37) / 0.028) ** 2)
                        + 0.24 * math.exp(-((beat_phase - 0.60) / 0.09) ** 2)
                    )
                else:
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
                fill="#8fcbb6" if use_mock_visuals else "#35e0c1",
                width=2.5 if use_mock_visuals else 2,
                smooth=True,
                tags="wave",
            )
            if not use_mock_visuals:
                self.ecg_canvas.create_line(
                    0, middle, width, middle,
                    fill="#23444a", width=1, tags="wave"
                )

        self.after(50, self._animate_ecg)

    def append_log(self, text: str) -> None:
        print(text)


# =============================================================================
# MÓDULO DE CONTROL Y EVENTOS (LÓGICA / CONTROLADOR)
# =============================================================================
class HapticUIController:
    """
    Controlador que maneja el flujo de la aplicación, interacción del usuario,
    el orquestador lógico (worker) y la actualización unificada de telemetría.
    """
    def select_policy_manual(self, policy: str) -> None:
        if self.auto_var.get():
            self.auto_var.set(False)
            self.toggle_auto_mode()
        self.sequential_simulation = False
        if self.is_mock:
            self.ecg_policy = policy
            simulation = SEQUENTIAL_SIMULATION[policy]
            self.ecg_bpm = float(simulation["bpm"])
            self.ecg_amplitude = float(simulation["amplitude"])
            self.ecg_signal_ok = True
            self.lbl_bpm.configure(text=f"BPM: {round(self.ecg_bpm)}")
        self.highlight_button(policy)
        self.worker.send_policy(policy)
        self.lbl_active_policy.configure(text=f"Política Activa: {policy.upper()}")
        self.update_displayed_image(policy)

    def stop_playback(self) -> None:
        if self.auto_var.get():
            self.auto_var.set(False)
            self.toggle_auto_mode()
        self.worker.stop_motors()
        self.sequential_simulation = False
        if self.is_mock:
            self.ecg_policy = None
            self.ecg_signal_ok = False
            self.ecg_bpm = 0.0
            self.ecg_amplitude = 0.0
            self.lbl_bpm.configure(text="BPM: 0")
            self.lbl_smooth.configure(text="Sin pulso")
            self.lbl_delta.configure(text="Sin política activa")
        self.lbl_active_policy.configure(text="Política Activa: DETENIDO")
        self.highlight_button("")
        self.update_displayed_image(None)

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
        self.after(
            0,
            lambda: self._update_auto_ui(policy) if self.sequential_simulation else None,
        )

    def _update_auto_ui(self, policy: str) -> None:
        simulation = SEQUENTIAL_SIMULATION[policy]
        self.ecg_policy = policy
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

    def update_telemetry(self, data: Dict[str, str]) -> None:
        def update() -> None:
            # OVERRIDE con delta falso si estamos en Modo Automático
            if self.auto_var.get() and self.orchestrator:
                data["phase"] = "run"
                data["signal_ok"] = "1"
                fake_d = self.orchestrator.fake_delta
                data['delta'] = str(int(fake_d))
                
                if fake_d >= 33: suggested = "calm_down"
                elif fake_d >= 19: suggested = "breath"
                elif fake_d >= 9: suggested = "reassure"
                else: suggested = "awareness"
                data['policy'] = suggested
                
                data['baseline_bpm'] = '70'
                data['bpm'] = str(70 + int(fake_d))

            if self.is_mock and self.ecg_policy is None and not self.auto_var.get():
                self.ecg_signal_ok = False
                self.ecg_bpm = 0.0
                self.ecg_amplitude = 0.0
                self.lbl_bpm.configure(text="BPM: 0")
                self.lbl_smooth.configure(text="Sin pulso")
                self.lbl_delta.configure(text="Sin política activa")
                return
            if self.is_mock and data.get("signal_ok") != "1":
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

            if self.auto_var.get():
                suggested = data.get("policy")
                current = self.lbl_active_policy.cget("text").split(": ")[-1].lower()
                if suggested in VALID_POLICIES and suggested != current:
                    is_initial_sync = current not in VALID_POLICIES
                    self.worker.send_policy(suggested)
                    self._update_auto_ui(suggested)
                    if self.orchestrator and not is_initial_sync:
                        self.orchestrator.policy_changed_event.set()

        self.after(0, update)


# =============================================================================
# APLICACIÓN PRINCIPAL (ENSAMBLADOR MVC)
# =============================================================================
class HapticDemoApp(ctk.CTk, HapticUIView, HapticUIController):
    """
    Clase principal que hereda de CustomTkinter, la Vista y el Controlador.
    Mantiene la firma original exacta y ensambla la aplicación.
    """
    def __init__(self, worker: SerialWorkerThread, is_mock: bool = False):
        super().__init__()
        self.worker = worker
        self.is_mock = is_mock
        self.orchestrator: Optional[DemoOrchestrator] = None
        suffix = " (MODO SIMULADOR / MOCK)" if is_mock else ""
        self.title(f"Pulso Háptico - Panel de Control Demo{suffix}")
        self.geometry("850x780")
        self.configure(fg_color="#1a1e24")
        self.worker.on_telemetry_received = self.update_telemetry
        self.worker.on_log_message = self.append_log
        
        # Variables de estado y animación
        self.ecg_bpm = 70.0
        self.ecg_amplitude = 0.0
        self.ecg_policy: Optional[str] = None
        self.ecg_target_bpm = 70.0
        self.ecg_target_amplitude = 0.0
        self.ecg_transition_started_at = time.monotonic()
        self.ecg_transition_from_bpm = 70.0
        self.ecg_transition_from_amplitude = 0.0
        self.ecg_signal_ok = False
        self.sequential_simulation = False
        
        # Inicialización de interfaces y rutinas
        self._build_ui(is_mock)
        self._animate_ecg()


def main() -> int:
    parser = argparse.ArgumentParser(description="Panel de control del pulso háptico (modo mock o hardware real).")
    parser.add_argument("--mock", action="store_true", help="Ejecuta la UI con el simulador del Arduino")
    parser.add_argument("--port", help="Puerto Serial real (ej. /dev/ttyUSB0 o COM5)")
    parser.add_argument("--baud", type=int, default=115200, help="Velocidad del puerto serial")
    parser.add_argument("--catalog", default="patterns", help="Carpeta con los patrones JSON")
    args = parser.parse_args()

    try:
        catalog = load_catalog(Path(args.catalog))
    except Exception as exc:
        print(f"[ERROR] Falló la carga del catálogo: {exc}")
        return 1

    if args.mock:
        ser_instance = MockArduinoSerial()
    else:
        try:
            import serial
        except ImportError:
            print("ERROR: falta instalar pyserial. Ejecutá: pip install pyserial", file=sys.stderr)
            return 1

        if not args.port:
            print("[ERROR] No se seleccionó puerto. Si no tienes hardware, usa --mock")
            return 1

        try:
            ser_instance = serial.Serial(port=args.port, baudrate=args.baud, timeout=1.0)
            time.sleep(2.0)
            ser_instance.reset_input_buffer()
        except serial.SerialException as exc:
            print(f"[ERROR] No se pudo abrir puerto {args.port}: {exc}")
            return 1

    worker = SerialWorkerThread(ser_instance, catalog)
    worker.start()
    app = HapticDemoApp(worker, is_mock=args.mock)

    def on_closing() -> None:
        if app.orchestrator:
            app.orchestrator.stop_demo()
        worker.stop()
        app.destroy()

    app.protocol("WM_DELETE_WINDOW", on_closing)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())