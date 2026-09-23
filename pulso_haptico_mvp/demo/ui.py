import customtkinter as ctk
import tkinter as tk
from typing import Callable, Dict, Optional
from hardware import MockArduinoSerial, SerialWorkerThread
from config import VALID_POLICIES, DEMO_STEP_DURATION_SEC
import threading
import time
from PIL import Image

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# =============================================================================
# ORQUESTADOR MODO AUTOMÁTICO
# =============================================================================
class DemoOrchestrator(threading.Thread):
    def __init__(self, worker: SerialWorkerThread, on_change_cb: Callable[[str, int], None], on_tick_cb: Callable[[int], None]):
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
            super().__init__(daemon=True)
            self.start()

    def stop_demo(self) -> None:
        self.running = False

    def run(self) -> None:
        direction = 1  
        
        while self.running:
            is_mock = hasattr(self.worker.ser, "target_delta")
            if is_mock:
                current_d = getattr(self.worker.ser, "current_delta", 0.0)
                
                if current_d >= 33.5:
                    direction = -1
                elif current_d <= 8.5:
                    direction = 1

                if direction == 1:
                    if current_d < 9.0:
                        if current_d < 2.0:
                            self.worker.ser.target_delta = 9.0
                        else:
                            self.worker.ser.target_delta = 19.0
                    elif current_d < 19.0:
                        self.worker.ser.target_delta = 19.0
                    elif current_d < 33.0:
                        self.worker.ser.target_delta = 33.0
                    else:
                        self.worker.ser.target_delta = 34.0
                else:
                    if current_d > 33.0:
                        self.worker.ser.target_delta = 18.5
                    elif current_d > 19.0:
                        self.worker.ser.target_delta = 18.5
                    elif current_d > 9.0:
                        self.worker.ser.target_delta = 8.5
                    else:
                        self.worker.ser.target_delta = 8.0
            else:
                policy = VALID_POLICIES[self.current_policy_index]
                self.worker.send_policy(policy)
                self.on_change_cb(policy, int(DEMO_STEP_DURATION_SEC))

            start_time = time.time()
            while time.time() - start_time < DEMO_STEP_DURATION_SEC:
                if not self.running:
                    return
                if self.policy_changed_event.is_set():
                    self.policy_changed_event.clear()
                    break
                remaining = int(DEMO_STEP_DURATION_SEC - (time.time() - start_time))
                self.on_tick_cb(remaining)
                time.sleep(0.2)

            self.current_policy_index = (self.current_policy_index + 1) % len(VALID_POLICIES)

# =============================================================================
# FRONTEND - INTERFAZ GRÁFICA CUSTOMTKINTER (CON IMÁGENES)
# =============================================================================
class HapticDemoApp(ctk.CTk):
    def __init__(self, worker: SerialWorkerThread, is_mock: bool = False):
        super().__init__()
        self.worker = worker
        self.orchestrator: Optional[DemoOrchestrator] = None

        title_suffix = " (MODO SIMULADOR / MOCK)" if is_mock else ""
        self.title(f"Pulso Háptico - Panel de Control Demo{title_suffix}")
        self.geometry("850x780")
        self.configure(fg_color="#1a1e24")

        self.worker.on_telemetry_received = self.update_telemetry
        self.worker.on_log_message = self.append_log 

        self.setup_ui(is_mock)

    def setup_ui(self, is_mock: bool) -> None:
        if is_mock:
            mock_banner = ctk.CTkLabel(
                self, text="⚠️ EJECUTANDO EN MODO MOCK (SIN ARDUINO CONECTADO)",
                text_color="black", fg_color="#ff9800", font=("Roboto", 13, "bold"), corner_radius=8
            )
            mock_banner.pack(fill="x", padx=20, pady=(15, 0))

        title = ctk.CTkLabel(
            self, text="DEMO CONTROL DE POLÍTICAS HÁPTICAS", 
            font=("Roboto", 22, "bold"), text_color="#00ADB5"
        )
        title.pack(pady=(15, 10))

        # Panel Secuencia Automática
        auto_frame = ctk.CTkFrame(self, fg_color="#2a3038", corner_radius=12)
        auto_frame.pack(fill="x", padx=20, pady=5)

        self.auto_var = tk.BooleanVar(value=False)
        self.auto_switch = ctk.CTkSwitch(
            auto_frame, text="Modo Secuencia Automática (30s)", variable=self.auto_var,
            font=("Roboto", 15, "bold"), text_color="#EEEEEE", progress_color="#00ADB5",
            command=self.toggle_auto_mode
        )
        self.auto_switch.pack(side="left", padx=20, pady=15)

        self.timer_label = ctk.CTkLabel(
            auto_frame, text="Timer: --s", font=("Roboto", 15, "bold"), text_color="#00ADB5"
        )
        self.timer_label.pack(side="right", padx=20)

        # Botones Manuales
        btn_frame = ctk.CTkFrame(self, fg_color="#1f242b", border_width=2, border_color="#2a3038", corner_radius=12)
        btn_frame.pack(fill="x", padx=20, pady=5)
        
        btn_title = ctk.CTkLabel(btn_frame, text="Selección Manual de Política", font=("Roboto", 14, "bold"), text_color="#EEEEEE")
        btn_title.pack(pady=(10, 5))

        btn_container = ctk.CTkFrame(btn_frame, fg_color="transparent")
        btn_container.pack(fill="x", padx=15, pady=5)

        self.buttons: Dict[str, ctk.CTkButton] = {}
        colors = {"reassure": "#2e7d32", "awareness": "#f9a825", "breath": "#1565c0", "calm_down": "#c62828"}
        hover_colors = {"reassure": "#1b5e20", "awareness": "#f57f17", "breath": "#0d47a1", "calm_down": "#b71c1c"}

        for policy in VALID_POLICIES:
            btn = ctk.CTkButton(
                btn_container, text=policy.upper(), font=("Roboto", 14, "bold"),
                fg_color=colors[policy], hover_color=hover_colors[policy], corner_radius=8,
                command=lambda p=policy: self.select_policy_manual(p)
            )
            btn.pack(side="left", expand=True, fill="x", padx=8)
            self.buttons[policy] = btn

        stop_btn = ctk.CTkButton(
            btn_container, text="STOP", font=("Roboto", 14, "bold"),
            fg_color="#333333", hover_color="#111111", text_color="#ff4444",
            corner_radius=8, command=self.stop_playback, width=90
        )
        stop_btn.pack(side="right", padx=8)

        # Monitor Telemetría
        tel_frame = ctk.CTkFrame(self, fg_color="#1f242b", border_width=2, border_color="#2a3038", corner_radius=12)
        tel_frame.pack(fill="x", padx=20, pady=5)
        
        self.lbl_bpm = ctk.CTkLabel(tel_frame, text="BPM: --", font=("Roboto", 16))
        self.lbl_bpm.grid(row=0, column=0, padx=20, pady=10, sticky="ew")

        self.lbl_smooth = ctk.CTkLabel(tel_frame, text="Undefined: --", font=("Roboto", 16))
        self.lbl_smooth.grid(row=0, column=1, padx=20, pady=10, sticky="ew")

        self.lbl_delta = ctk.CTkLabel(tel_frame, text="Undefined: --", font=("Roboto", 16))
        self.lbl_delta.grid(row=0, column=2, padx=20, pady=10, sticky="ew")

        self.lbl_active_policy = ctk.CTkLabel(
            tel_frame, text="Política Activa: NINGUNA", 
            font=("Roboto", 16, "bold"), text_color="#00ADB5"
        )
        self.lbl_active_policy.grid(row=1, column=0, columnspan=3, pady=(0, 10))
        tel_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # SECCIÓN DE IMÁGENES (Reemplaza a la consola)
        self.image_frame = ctk.CTkFrame(self, fg_color="#1f242b", border_width=2, border_color="#2a3038", corner_radius=12)
        self.image_frame.pack(fill="both", expand=True, padx=20, pady=(5, 20))

        self.image_label = ctk.CTkLabel(self.image_frame, text="Selecciona una política para visualizar su estado", font=("Roboto", 16, "italic"), text_color="#888888")
        self.image_label.pack(expand=True, pady=10)

        # Cargar las imágenes en memoria
        self.policy_images = {
            "reassure": "Demo para 189 (3).jpg",
            "awareness": "Demo para 189.jpg",
            "breath": "Demo para 189 (1).jpg",
            "calm_down": "Demo para 189 (2).jpg"
        }
        
        self.ctk_images = {}
        for policy, img_path in self.policy_images.items():
            try:
                img = Image.open(img_path)
                # Ajustamos el tamaño para que encaje bien en la ventana (Ancho, Alto)
                self.ctk_images[policy] = ctk.CTkImage(light_image=img, dark_image=img, size=(450, 300))
            except Exception as e:
                print(f"No se pudo cargar la imagen {img_path}: {e}")
                self.ctk_images[policy] = None

    def update_displayed_image(self, policy: str) -> None:
        img = self.ctk_images.get(policy)
        if img:
            self.image_label.configure(image=img, text="")
        else:
            self.image_label.configure(image="", text="Imagen no encontrada")

    def select_policy_manual(self, policy: str) -> None:
        if self.auto_var.get():
            self.auto_var.set(False)
            self.toggle_auto_mode()
        
        self.highlight_button(policy)
        self.worker.send_policy(policy)
        self.lbl_active_policy.configure(text=f"Política Activa: {policy.upper()}")
        self.update_displayed_image(policy)

    def highlight_button(self, policy: str) -> None:
        for p, btn in self.buttons.items():
            if p == policy:
                btn.configure(border_width=3, border_color="#FFFFFF")
            else:
                btn.configure(border_width=0)

    def stop_playback(self) -> None:
        if self.auto_var.get():
            self.auto_var.set(False)
            self.toggle_auto_mode()
        self.worker.stop_motors()
        self.lbl_active_policy.configure(text="Política Activa: DETENIDO")
        self.highlight_button("")
        self.image_label.configure(image="", text="Detenido - Sin política activa")

    def toggle_auto_mode(self) -> None:
        if self.auto_var.get():
            self.orchestrator = DemoOrchestrator(
                self.worker, 
                on_change_cb=self.on_auto_policy_change,
                on_tick_cb=self.on_auto_tick
            )
            self.orchestrator.start_demo()
        else:
            if self.orchestrator:
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
        def _update():
            signal_ok = data.get("signal_ok")
            if signal_ok == "1":
                self.lbl_bpm.configure(text=f"BPM: {data.get('bpm', '--')}")
                if data.get("phase") == "run":
                    self.lbl_smooth.configure(text=f"Baseline: {data.get('baseline_bpm', '--')}")
                    self.lbl_delta.configure(text=f"Delta: {data.get('delta', '--')}")
                else:
                    self.lbl_smooth.configure(text=f"Beat average: {data.get('beat_avg', '--')}")
                    self.lbl_delta.configure(text=f"Samples: {data.get('baseline_samples', '--')}")
                
                if self.auto_var.get() and hasattr(self.worker.ser, "target_delta"):
                    suggested_policy = data.get("policy")
                    current_active = self.lbl_active_policy.cget("text")
                    current_policy = current_active.split(": ")[-1].lower() if ": " in current_active else ""
                    
                    if suggested_policy and suggested_policy in VALID_POLICIES and suggested_policy != current_policy:
                        self.worker.send_policy(suggested_policy)
                        self._update_auto_ui(suggested_policy)
                        if self.orchestrator:
                            self.orchestrator.policy_changed_event.set()

        self.after(0, _update)

    def append_log(self, text: str) -> None:
        # Imprime en la consola del sistema para no romper el hilo de SerialWorkerThread
        print(text)

if __name__ == "__main__":
    # 1. Iniciamos el hardware simulado y el worker thread
    mock_serial = MockArduinoSerial()
    worker = SerialWorkerThread(mock_serial, catalog={})
    worker.start()

    # 2. Iniciamos la interfaz gráfica en modo Mock (simulador)
    app = HapticDemoApp(worker, is_mock=True)
    app.mainloop()

    # 3. Al cerrar la ventana, detenemos los hilos
    worker.stop()