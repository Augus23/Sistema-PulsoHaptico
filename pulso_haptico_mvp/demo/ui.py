import argparse
import threading
import time
import math
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import customtkinter as ctk
import tkinter as tk
from PIL import Image

from demo.config import EffectivePattern
from demo.hardware import MockArduinoSerial, SerialWorkerThread
from demo.protocol import build_effective_pattern, load_catalog
from demo.constants import (
    DEMO_STEP_DURATION_SEC,
    SEQUENTIAL_POLICIES,
    BPM_CONFIG,
    VALID_POLICIES,
    POLICY_LABELS,
    POLICY_SCENARIOS,
    MOCK_ECG_POLICY_LEVELS,
    MOTOR_POLICY_DESCRIPTIONS,
    POLICY_COLORS,
)



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
        self.fake_bpm = float(BPM_CONFIG[SEQUENTIAL_POLICIES[0]]["bpm"])

    def start_demo(self) -> None:
        if not self.running:
            self.running = True
            super().__init__(daemon=True)
            self.start()

    def stop_demo(self) -> None:
        self.running = False
        self.policy_changed_event.set()

    def run(self) -> None:
        self.current_policy_index = 0
        direction = 1  # 1 = forward (index increases), -1 = backward (index decreases)
        n = len(SEQUENTIAL_POLICIES)

        # Start fake_bpm at the first policy's target
        self.fake_bpm = float(BPM_CONFIG[SEQUENTIAL_POLICIES[0]]["bpm"])

        while self.running:
            current_policy = SEQUENTIAL_POLICIES[self.current_policy_index]
            target_bpm = float(BPM_CONFIG[current_policy]["bpm"])

            # Notify UI that a new policy step is starting
            self.on_change_cb(current_policy, int(DEMO_STEP_DURATION_SEC))

            # Linear ramp: fake_bpm goes from its current value to target_bpm
            # over exactly DEMO_STEP_DURATION_SEC seconds, clamped once reached
            start_bpm = self.fake_bpm
            bpm_rate = (target_bpm - start_bpm) / DEMO_STEP_DURATION_SEC

            start_time = time.time()

            while time.time() - start_time < DEMO_STEP_DURATION_SEC:
                if not self.running:
                    return
                if self.policy_changed_event.is_set():
                    self.policy_changed_event.clear()
                    break

                now = time.time()
                elapsed = now - start_time

                # Animate fake_bpm; clamp so it never overshoots the target
                new_bpm = start_bpm + bpm_rate * elapsed
                if bpm_rate >= 0:
                    self.fake_bpm = min(new_bpm, target_bpm)
                else:
                    self.fake_bpm = max(new_bpm, target_bpm)

                remaining = max(0, int(math.ceil(DEMO_STEP_DURATION_SEC - elapsed)))
                self.on_tick_cb(remaining)
                time.sleep(0.1)

            if not self.running:
                return

            # Snap to target exactly at step end
            self.fake_bpm = target_bpm

            # Advance policy index with ping-pong:
            # change direction first when hitting the boundary, then move
            if direction == 1:
                if self.current_policy_index >= n - 1:
                    direction = -1
                    self.current_policy_index -= 1
                else:
                    self.current_policy_index += 1
            else:
                if self.current_policy_index <= 0:
                    direction = 1
                    self.current_policy_index += 1
                else:
                    self.current_policy_index -= 1




# =============================================================================
# MÓDULO DE INTERFAZ GRÁFICA (VISTA)
# =============================================================================
class HapticUIView:
    """
    Clase responsable exclusivamente de la inicialización, manipulación visual,
    imágenes, animaciones de canvas y actualización gráfica (CustomTkinter).
    """
   

    # Drop-in replacement for HapticUIView._build_ui (everything else in the file stays untouched).
    def _build_ui(self, is_mock: bool) -> None:
        # ---- Root layout: left column (everything) + right column (motors grid) ----
        self.grid_columnconfigure(0, weight=11, uniform="main_cols")
        self.grid_columnconfigure(1, weight=9, uniform="main_cols")
        self.grid_rowconfigure(0, weight=1)

        left_panel = ctk.CTkFrame(self, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew")

        motor_panel = ctk.CTkFrame(
            self, fg_color="#1f242b", border_width=2, border_color="#2a3038",
            corner_radius=12, width=100,
        )
        motor_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=(8, 14))
        motor_panel.grid_propagate(False)
        motor_panel.grid_columnconfigure(0, weight=1)
        motor_panel.grid_rowconfigure(0, weight=1)

        # ---- LEFT SIDE ----
        if is_mock:
            ctk.CTkLabel(
                left_panel,
                text="MODO MOCK: SIN ARDUINO CONECTADO",
                text_color="black",
                fg_color="#ff9800",
                font=("Roboto", 15, "bold"),
                height=34,
                corner_radius=8,
            ).pack(fill="x", padx=20, pady=(8, 0))

        ctk.CTkLabel(
            left_panel,
            text="DEMO CONTROL DE POLÍTICAS HÁPTICAS",
            font=("Roboto", 26, "bold"),
            text_color="#00ADB5",
        ).pack(pady=(8, 4))

        auto_frame = ctk.CTkFrame(left_panel, fg_color="#2a3038", corner_radius=12)
        auto_frame.pack(fill="x", padx=20, pady=4)
        self.auto_var = tk.BooleanVar(value=False)
        ctk.CTkSwitch(
            auto_frame,
            text=f"Modo Secuencia Automática ({DEMO_STEP_DURATION_SEC}s)",
            variable=self.auto_var,
            font=("Roboto", 17, "bold"),
            switch_width=48,
            switch_height=24,
            text_color="#EEEEEE",
            progress_color="#00ADB5",
            command=self.toggle_auto_mode,
        ).pack(side="left", padx=18, pady=10)
        self.timer_label = ctk.CTkLabel(
            auto_frame, text="Timer: --s", font=("Roboto", 17, "bold"), text_color="#00ADB5"
        )
        self.timer_label.pack(side="right", padx=18)

        telemetry_frame = ctk.CTkFrame(
            left_panel, fg_color="#1f242b", border_width=2, border_color="#2a3038", corner_radius=12
        )
        telemetry_frame.pack(fill="x", padx=20, pady=4)
        self.lbl_bpm = ctk.CTkLabel(telemetry_frame, text="BPM: --", font=("Roboto", 18, "bold"), anchor="w")
        self.lbl_smooth = ctk.CTkLabel(telemetry_frame, text="Undefined: --", font=("Roboto", 18, "bold"), anchor="center")
        self.lbl_delta = ctk.CTkLabel(telemetry_frame, text="Undefined: --", font=("Roboto", 18, "bold"), anchor="e")
        self.lbl_bpm.grid(row=0, column=0, padx=(14, 4), pady=(6, 2), sticky="ew")
        self.lbl_smooth.grid(row=0, column=1, padx=4, pady=(6, 2), sticky="ew")
        self.lbl_delta.grid(row=0, column=2, padx=(4, 14), pady=(6, 2), sticky="ew")
        telemetry_frame.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(
            telemetry_frame,
            text="MONITOR DE PULSO",
            font=("Roboto", 13, "bold"),
            text_color="#00ADB5",
        ).grid(row=1, column=0, columnspan=3, pady=(2, 2))
        self.ecg_canvas = tk.Canvas(
            telemetry_frame,
            height=160,
            bg="#10161b",
            highlightthickness=1,
            highlightbackground="#2a3038",
        )
        self.ecg_canvas.grid(row=2, column=0, columnspan=3, padx=12, pady=(2, 8), sticky="ew")
        telemetry_frame.grid_rowconfigure(2, weight=1)

        # ---- Buttons: policies in a 2x2 grid, STOP / VER IMÁGENES on the right ----
        button_frame = ctk.CTkFrame(
            left_panel, fg_color="#1f242b", border_width=2, border_color="#2a3038", corner_radius=12
        )
        button_frame.pack(fill="x", padx=20, pady=4)
        button_container = ctk.CTkFrame(button_frame, fg_color="transparent")
        button_container.pack(fill="x", padx=12, pady=8)
        button_container.grid_columnconfigure(0, weight=1)
        button_container.grid_columnconfigure(1, weight=0)

        policy_grid = ctk.CTkFrame(button_container, fg_color="transparent")
        policy_grid.grid(row=0, column=0, sticky="nsew")
        policy_grid.grid_columnconfigure((0, 1), weight=1, uniform="policy_col")

        self.buttons: Dict[str, ctk.CTkButton] = {}
        for index, policy in enumerate(VALID_POLICIES):
            button = ctk.CTkButton(
                policy_grid,
                text=POLICY_LABELS[policy],
                font=("Roboto", 15, "bold"),
                height=46,
                fg_color=POLICY_COLORS[policy],
                hover_color=POLICY_COLORS[policy],
                text_color="#FFFFFF",
                corner_radius=8,
                command=lambda selected=policy: self.select_policy_manual(selected),
            )
            button.grid(row=index // 2, column=index % 2, padx=5, pady=5, sticky="ew")
            self.buttons[policy] = button

        side_buttons = ctk.CTkFrame(button_container, fg_color="transparent")
        side_buttons.grid(row=0, column=1, sticky="ns", padx=(5, 0))
        side_buttons.grid_columnconfigure(0, weight=1)
        side_buttons.grid_rowconfigure((0, 1), weight=1)
        ctk.CTkButton(
            side_buttons,
            text="VER IMÁGENES",
            font=("Roboto", 15, "bold"),
            fg_color="#605F5E",
            hover_color="#605F5E",
            text_color="#FFFFFF",
            corner_radius=8,
            height=46,
            command=self.open_policy_gallery,
        ).grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(
            side_buttons,
            text="STOP",
            font=("Roboto", 15, "bold"),
            fg_color="#333333",
            hover_color="#111111",
            text_color="#ff4444",
            corner_radius=8,
            height=46,
            command=self.stop_playback,
        ).grid(row=1, column=0, padx=5, pady=5, sticky="ew")

        # ---- Policy info (left) ----
        self.image_frame = ctk.CTkFrame(
            left_panel, fg_color="#1f242b", border_width=2, border_color="#2a3038", corner_radius=12
        )
        self.image_frame.pack(fill="both", expand=True, padx=20, pady=(4, 14))
        self.image_frame.grid_columnconfigure(0, weight=1)
        self.image_frame.grid_rowconfigure(0, weight=1)

        # ---- RIGHT SIDE: motors grid, fills the full height ----
        self.motor_canvas = tk.Canvas(
            motor_panel,
            width=100,
            bg="#10161b",
            highlightthickness=1,
            highlightbackground="#2a3038",
        )
        self.motor_canvas.grid(row=0, column=0, padx=14, pady=14, sticky="nsew")
        self.motor_canvas.bind("<Configure>", self._resize_policy_content)

        self.motor_info_frame = ctk.CTkFrame(self.image_frame, fg_color="transparent")
        self.motor_info_frame.grid(
            row=0, column=0, padx=(10, 18), pady=18, sticky="nsew"
        )
        self.motor_info_frame.grid_columnconfigure(0, weight=1)
        self.motor_info_frame.grid_rowconfigure(0, weight=0)
        self.motor_info_frame.grid_rowconfigure(1, weight=1)

        self.motor_policy_label = ctk.CTkLabel(
            self.motor_info_frame,
            text="Política Activa:\nNINGUNA",
            font=("Roboto", 22, "bold"),
            text_color="#00ADB5",
            justify="center",
            wraplength=300,
        )
        self.motor_policy_label.pack(pady=(10, 14), fill="x")

        self.motor_policy_description_label = ctk.CTkLabel(
            self.motor_info_frame,
            text="",
            font=("Roboto", 22),
            text_color="#D2D8D6",
            anchor="center",
            justify="center",
            wraplength=300,
        )
        self.motor_policy_description_label.pack(fill="both", expand=True, padx=10)

        self.scenario_level_label = ctk.CTkLabel(
            self.image_frame,
            text="SIN POLITICA ACTIVA",
            font=("Roboto", 16, "bold"),
            text_color="#00ADB5",
            anchor="w",
            justify="left",
        )
        self.scenario_level_label.grid(row=1, column=0, padx=(8, 16), pady=(18, 2), sticky="ew")
        self.scenario_title_label = ctk.CTkLabel(
            self.image_frame,
            text="Escenas cotidianas",
            font=("Roboto", 28, "bold"),
            text_color="#EEEEEE",
            anchor="w",
            justify="left",
            wraplength=320,
        )
        self.scenario_title_label.grid(row=2, column=0, padx=(8, 16), pady=(0, 8), sticky="ew")
        self.scenario_description_label = ctk.CTkLabel(
            self.image_frame,
            text="Selecciona una politica para ver una situacion posible asociada a ella.",
            font=("Roboto", 20),
            text_color="#D2D8D6",
            anchor="nw",
            justify="left",
            wraplength=320,
        )
        self.scenario_description_label.grid(row=3, column=0, padx=(8, 16), pady=(0, 12), sticky="new")
        self.scenario_support_label = ctk.CTkLabel(
            self.image_frame,
            text="ACOMPAÑAMIENTO HAPTICO",
            font=("Roboto", 16, "bold"),
            text_color="#9FC7B7",
            anchor="w",
        )
        self.scenario_support_label.grid(row=4, column=0, padx=(8, 16), pady=(4, 2), sticky="ew")
        self.scenario_response_label = ctk.CTkLabel(
            self.image_frame,
            text="",
            font=("Roboto", 20),
            text_color="#D2D8D6",
            anchor="nw",
            justify="left",
            wraplength=320,
        )
        self.scenario_response_label.grid(row=5, column=0, padx=(8, 16), pady=(0, 10), sticky="new")
        self.scenario_note_label = ctk.CTkLabel(
            self.image_frame,
            text="Ejemplos ilustrativos; cada persona vive los estimulos de manera distinta.",
            font=("Roboto", 15, "italic"),
            text_color="#899895",
            anchor="w",
            justify="left",
            wraplength=320,
        )
        self.scenario_note_label.grid(row=6, column=0, padx=(8, 16), pady=(0, 16), sticky="ew")
        for label in (
            self.scenario_level_label,
            self.scenario_title_label,
            self.scenario_description_label,
            self.scenario_support_label,
            self.scenario_response_label,
            self.scenario_note_label,
        ):
            label.grid_remove()

        # Keep the policy texts inside the panel: wrap them to the available width.
        wrap_state = {"value": 300}

        def _update_text_wrap(event) -> None:
            wrap = max(150, event.width - 70)
            if wrap == wrap_state["value"]:
                return
            wrap_state["value"] = wrap
            for wrapped in (
                self.motor_policy_label,
                self.motor_policy_description_label,
                self.scenario_title_label,
                self.scenario_description_label,
                self.scenario_response_label,
                self.scenario_note_label,
            ):
                wrapped.configure(wraplength=wrap)

        self.image_frame.bind("<Configure>", _update_text_wrap, add="+")

        self.displayed_policy: Optional[str] = None
        self.motor_active_motors: set[int] = set()
        self.motor_sequence_token = 0
        self.motor_animation_after_id: Optional[str] = None
        self.policy_gallery_window: Optional[ctk.CTkToplevel] = None
        self.policy_gallery_images: list[ctk.CTkImage] = []
        self.update_displayed_image(None)
        self.image_frame.bind("<Configure>", self._resize_policy_content, add="+")

    def open_policy_gallery(self) -> None:
        if self.policy_gallery_window is not None and self.policy_gallery_window.winfo_exists():
            self.policy_gallery_window.focus()
            return

        gallery = ctk.CTkToplevel(self)
        gallery.title("Imágenes de políticas")
        gallery.geometry("1100x640")
        gallery.minsize(480, 320)
        gallery.configure(fg_color="#1a1e24")
        self.policy_gallery_window = gallery
        self.policy_gallery_images = []

        ctk.CTkLabel(
            gallery,
            text="Del reconocimiento sutil a la contención en estados de alta activación sensorial",
            font=("Roboto", 22, "bold"),
            text_color="#00ADB5",
        ).pack(pady=(18, 12))

        grid_frame = ctk.CTkFrame(gallery, fg_color="#1a1e24")
        grid_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        grid_frame.grid_rowconfigure((0, 1), weight=1)
        grid_frame.grid_columnconfigure((0, 1), weight=1)

        # 2x2 grid: top (awareness, reassure), bottom (breath, calm_down)
        policies_grid = [
            ("awareness", 0, 0),
            ("reassure", 0, 1),
            ("breath", 1, 0),
            ("calm_down", 1, 1),
        ]

        image_files = {
            "awareness": "static/awareness.jpg",
            "reassure": "static/reassure.jpg",
            "breath": "static/breath.jpg",
            "calm_down": "static/calm_down.jpg",
        }

        ctk_images: Dict[str, ctk.CTkImage] = {}
        static_base = Path(__file__).resolve().parent
        cell_pad = 10

        for policy, row, col in policies_grid:
            lbl = ctk.CTkLabel(grid_frame, text="", fg_color="transparent")
            lbl.grid(row=row, column=col, padx=cell_pad, pady=cell_pad, sticky="nsew")

            image_path = static_base / image_files[policy]
            try:
                pil_img = Image.open(image_path).copy()
                ctk_img = ctk.CTkImage(
                    light_image=pil_img,
                    dark_image=pil_img,
                    size=(520, 290),
                )
                self.policy_gallery_images.append(ctk_img)
                ctk_images[policy] = ctk_img
                lbl.configure(image=ctk_img)
            except (FileNotFoundError, OSError):
                lbl.configure(text=f"Imagen no encontrada\n({policy})")

        last_dimensions = [0, 0]
        resize_timer: list[Optional[str]] = [None]

        def _update_image_sizes() -> None:
            if not gallery.winfo_exists():
                return
            width = grid_frame.winfo_width()
            height = grid_frame.winfo_height()
            if width <= 10 or height <= 10:
                width = max(100, gallery.winfo_width() - 32)
                height = max(100, gallery.winfo_height() - 80)

            # Account for padding on each cell
            cell_w = max(20, (width - (cell_pad * 4)) // 2)
            cell_h = max(20, (height - (cell_pad * 4)) // 2)

            if (cell_w, cell_h) == (last_dimensions[0], last_dimensions[1]):
                return
            last_dimensions[0], last_dimensions[1] = cell_w, cell_h

            for ctk_img in ctk_images.values():
                ctk_img.configure(size=(cell_w, cell_h))

        def _on_window_configure(event) -> None:
            if event.widget != gallery:
                return
            if resize_timer[0] is not None:
                gallery.after_cancel(resize_timer[0])
            resize_timer[0] = gallery.after(15, _update_image_sizes)

        gallery.bind("<Configure>", _on_window_configure)

        def close_gallery() -> None:
            if resize_timer[0] is not None:
                gallery.after_cancel(resize_timer[0])
            self.policy_gallery_window = None
            self.policy_gallery_images = []
            gallery.destroy()

        gallery.protocol("WM_DELETE_WINDOW", close_gallery)
        gallery.after(30, _update_image_sizes)

    def _resize_policy_content(self, _event=None) -> None:
        panel_width = self.image_frame.winfo_width()
        panel_height = self.image_frame.winfo_height()
        if panel_width <= 1 or panel_height <= 1:
            return

        self._draw_motor_map(self.displayed_policy)

    def _draw_motor_map(self, policy: Optional[str]) -> None:
        width = max(self.motor_canvas.winfo_width(), 360)
        height = max(self.motor_canvas.winfo_height(), 260)
        self.motor_canvas.delete("motor")
        active_motors = self.motor_active_motors if policy else set()
        self.motor_canvas.create_text(
            width / 2,
            24,
            text="MAPA DE MOTORES",
            fill="#00ADB5",
            font=("Roboto", 13, "bold"),
            tags="motor",
        )
        radius = max(18, min(40, int(min(width, height) * 0.07)))
        left = width * 0.30
        right = width * 0.70
        top = 62
        bottom = height - 30
        self.motor_canvas.create_rectangle(
            left - radius - 11,
            top - 20,
            right + radius + 11,
            bottom + 20,
            outline="#607177",
            width=2,
            tags="motor",
        )
        positions = [
            (left, top),
            (left, (top + bottom) / 2),
            (left, bottom),
            (right, top),
            (right, (top + bottom) / 2),
            (right, bottom),
        ]
        for motor, (x, y) in enumerate(positions, start=1):
            active = motor in active_motors
            fill = "#00ADB5" if active else "#39464b"
            outline = "#8ee8da" if active else "#718087"
            self.motor_canvas.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill=fill, outline=outline, width=2, tags="motor"
            )
            self.motor_canvas.create_text(
                x, y, text=f"M{motor}", fill="#FFFFFF",
                font=("Roboto", 11, "bold"), tags="motor"
            )
    def _cancel_motor_sequence(self) -> None:
        self.motor_sequence_token += 1
        if self.motor_animation_after_id is not None:
            self.after_cancel(self.motor_animation_after_id)
            self.motor_animation_after_id = None
        self.motor_active_motors = set()

    def _start_motor_sequence(self, policy: str) -> None:
        self._cancel_motor_sequence()
        token = self.motor_sequence_token
        pattern = build_effective_pattern(self.worker.catalog[policy])
        self._show_motor_step(
            policy,
            pattern.human_steps,
            0,
            token,
            0,
            pattern.repeat_count,
            pattern.cooldown_ms,
        )

    def _show_motor_step(
        self,
        policy: str,
        steps: list[Dict[str, Any]],
        index: int,
        token: int,
        repeat_index: int,
        repeat_count: int,
        cooldown_ms: int,
    ) -> None:
        if token != self.motor_sequence_token or self.displayed_policy != policy:
            return

        if index >= len(steps):
            if repeat_index + 1 < repeat_count:
                self.motor_active_motors = set()
                self._draw_motor_map(policy)
                self.motor_animation_after_id = self.after(
                    cooldown_ms,
                    lambda: self._show_motor_step(
                        policy,
                        steps,
                        0,
                        token,
                        repeat_index + 1,
                        repeat_count,
                        cooldown_ms,
                    ),
                )
                return
            self.motor_active_motors = set()
            self.motor_animation_after_id = None
            self._draw_motor_map(policy)
            return

        step = steps[index]
        mask = int(step["mask"])
        self.motor_active_motors = {
            channel + 1 for channel in range(6) if mask & (1 << channel)
        }
        self._draw_motor_map(policy)
        self.motor_animation_after_id = self.after(
            int(step["duration_ms"]),
            lambda: self._show_motor_step(
                policy,
                steps,
                index + 1,
                token,
                repeat_index,
                repeat_count,
                cooldown_ms,
            ),
        )

    def update_displayed_image(self, policy: Optional[str]) -> None:
        self._cancel_motor_sequence()
        self.displayed_policy = policy
        if policy not in POLICY_SCENARIOS:
            self._draw_motor_map(None)
            self.motor_policy_description_label.configure(text="")
            self.scenario_level_label.configure(text="SIN POLITICA ACTIVA")
            self.scenario_title_label.configure(text="Escenas cotidianas")
            self.scenario_description_label.configure(
                text="Selecciona una politica para ver una situacion posible asociada a ella."
            )
            self.scenario_support_label.configure(text="ACOMPANAMIENTO HAPTICO")
            self.scenario_response_label.configure(text="")
            return

        self._draw_motor_map(policy)
        title, description, response = POLICY_SCENARIOS[policy]
        motor_description = MOTOR_POLICY_DESCRIPTIONS.get(policy, description)
        self.motor_policy_description_label.configure(text=motor_description)
        _, level_label = MOCK_ECG_POLICY_LEVELS[policy]
        self.scenario_level_label.configure(text=level_label)
        self.scenario_title_label.configure(text=title)
        self.scenario_description_label.configure(text=description)
        self.scenario_support_label.configure(text="ACOMPANAMIENTO HAPTICO")
        self.scenario_response_label.configure(text=response)
        self._resize_policy_content()

    def highlight_button(self, policy: str) -> None:
        for current, button in self.buttons.items():
            button.configure(border_width=3 if current == policy else 0, border_color="#FFFFFF")

    def _animate_ecg(self) -> None:
        width = max(self.ecg_canvas.winfo_width(), 400)
        height = max(self.ecg_canvas.winfo_height(), 125)
        middle = height / 2
        self.ecg_canvas.delete("wave")
        use_mock_visuals = self.is_mock or self.auto_var.get() or self.ecg_policy is not None

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
            if self.auto_var.get():
                period = 1.4
            else:
                period = 60.0 / bpm
            visible_seconds = 6.0
            now = time.time()
            if use_mock_visuals:
                amplitude, policy_label = MOCK_ECG_POLICY_LEVELS.get(
                    self.ecg_policy, MOCK_ECG_POLICY_LEVELS["reassure"]
                )
                visual_exaggeration = {
                    "awareness": 1.2,
                    "reassure": 1.8,
                    "breath": 1.9,
                    "calm_down": 2.5,
                }.get(self.ecg_policy, 1.0)
                amplitude *= visual_exaggeration
            else:
                amplitude = max(5.0, min(self.ecg_amplitude * 0.9, 38.0))
                policy_offset = {
                    "awareness": 0.0,
                    "reassure": 6.0,
                    "breath": 12.0,
                    "calm_down": 18.0,
                }.get(self.ecg_policy, 0.0)
                amplitude = min(amplitude + policy_offset, middle - 8.0)
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
                    font=("Roboto", 13, "bold"),
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
                    if self.ecg_policy == "calm_down":
                        pulse *= 2.15
                    elif self.ecg_policy == "breath":
                        pulse *= 1.55
                    elif self.ecg_policy == "reassure":
                        pulse *= 1.55
                    elif self.ecg_policy == "awareness":
                        pulse *= 1.25
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
        self.ecg_policy = policy
        if self.is_mock:
            self.ecg_policy = policy
            self.ecg_amplitude = float(BPM_CONFIG[policy]["amplitude"])
            self.ecg_bpm = float(BPM_CONFIG[policy]["bpm"])
            self.ecg_signal_ok = True
            self.lbl_bpm.configure(text=f"BPM: {round(self.ecg_bpm)}")
        self.highlight_button(policy)
        self.worker.send_policy(policy)
        self.motor_policy_label.configure(
            text=f"Política Activa:\n{POLICY_LABELS[policy]}"
        )
        self.update_displayed_image(policy)
        self._start_motor_sequence(policy)

    def stop_playback(self) -> None:
        if self.auto_var.get():
            self.auto_var.set(False)
            self.toggle_auto_mode()
        self.worker.stop_motors()
        self.sequential_simulation = False
        self.ecg_policy = None
        if self.is_mock:
            self.ecg_signal_ok = False
            self.ecg_bpm = 0.0
            self.ecg_amplitude = 0.0
            self.lbl_bpm.configure(text="BPM: 0")
            self.lbl_smooth.configure(text="Sin pulso")
            self.lbl_delta.configure(text="Sin política activa")
        self.motor_policy_label.configure(text="Política Activa:\nDETENIDO")
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
        self.ecg_policy = policy
        self.ecg_signal_ok = True
        self.ecg_transition_from_bpm = self.ecg_bpm
        self.ecg_transition_from_amplitude = self.ecg_amplitude
        self.ecg_target_bpm = float(BPM_CONFIG[policy]["bpm"])
        self.ecg_target_amplitude = float(BPM_CONFIG[policy]["amplitude"])        
        self.ecg_transition_started_at = time.monotonic()
        self.worker.send_policy(policy)
        self.highlight_button(policy)
        self.motor_policy_label.configure(
            text=f"Política Activa (AUTO):\n{POLICY_LABELS[policy]}"
        )
        self.update_displayed_image(policy)
        self._start_motor_sequence(policy)

    def on_auto_tick(self, remaining: int) -> None:
        self.after(0, lambda: self.timer_label.configure(text=f"Timer: {remaining}s"))

    def update_telemetry(self, data: Dict[str, str]) -> None:
        def update() -> None:
            # OVERRIDE con bpm falso si estamos en Modo Automático
            if self.auto_var.get() and self.orchestrator:
                data["phase"] = "run"
                data["signal_ok"] = "1"
                fake_bpm = self.orchestrator.fake_bpm
                baseline_bpm = 70
                data['delta'] = str(max(0, int(fake_bpm - baseline_bpm)))
                data['policy'] = SEQUENTIAL_POLICIES[self.orchestrator.current_policy_index]
                data['baseline_bpm'] = str(baseline_bpm)
                data['bpm'] = str(int(fake_bpm))

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
                self.lbl_smooth.configure(text=f"Pulso base: {data.get('baseline_bpm', '--')}")
                self.lbl_delta.configure(text=f"Delta: {data.get('delta', '--')}")
            else:
                self.lbl_smooth.configure(text=f"Pulso promedio: {data.get('beat_avg', '--')}")
                self.lbl_delta.configure(text=f"Muestras: {data.get('baseline_samples', '--')}")

            # Policy changes in auto mode are driven exclusively by the orchestrator
            # (via on_change_cb → _update_auto_ui). No reactive switch needed here.

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
        self.geometry("1200x780")
        self.minsize(1000, 700)
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


# def main() -> int:
#     parser = argparse.ArgumentParser(description="Panel de control del pulso háptico (modo mock o hardware real).")
#     parser.add_argument("--mock", action="store_true", help="Ejecuta la UI con el simulador del Arduino")
#     parser.add_argument("--port", help="Puerto Serial real (ej. /dev/ttyUSB0 o COM5)")
#     parser.add_argument("--baud", type=int, default=115200, help="Velocidad del puerto serial")
#     parser.add_argument("--catalog", default="patterns", help="Carpeta con los patrones JSON")
#     args = parser.parse_args()

#     try:
#         catalog = load_catalog(Path(args.catalog))
#     except Exception as exc:
#         print(f"[ERROR] Falló la carga del catálogo: {exc}")
#         return 1

#     if args.mock:
#         ser_instance = MockArduinoSerial()
#     else:
#         try:
#             import serial
#         except ImportError:
#             print("ERROR: falta instalar pyserial. Ejecutá: pip install pyserial", file=sys.stderr)
#             return 1

#         if not args.port:
#             print("[ERROR] No se seleccionó puerto. Si no tienes hardware, usa --mock")
#             return 1

#         try:
#             ser_instance = serial.Serial(port=args.port, baudrate=args.baud, timeout=1.0)
#             time.sleep(2.0)
#             ser_instance.reset_input_buffer()
#         except serial.SerialException as exc:
#             print(f"[ERROR] No se pudo abrir puerto {args.port}: {exc}")
#             return 1

#     worker = SerialWorkerThread(ser_instance, catalog)
#     worker.start()
#     app = HapticDemoApp(worker, is_mock=args.mock)

#     def on_closing() -> None:
#         if app.orchestrator:
#             app.orchestrator.stop_demo()
#         worker.stop()
#         app.destroy()

#     app.protocol("WM_DELETE_WINDOW", on_closing)
#     app.mainloop()
#     return 0


# if __name__ == "__main__":
#     sys.exit(main())