import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional
from demo.hardware import SerialWorkerThread
from demo.config import VALID_POLICIES, DEMO_STEP_DURATION_SEC
import threading
import time
import math



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
        direction = 1  # 1 = subiendo, -1 = bajando
        
        while self.running:
            # Identificar en qué política estamos basándonos en el UI
            current_active = self.worker.ser.target_delta if hasattr(self.worker.ser, "target_delta") else 0
            
            is_mock = hasattr(self.worker.ser, "target_delta")
            if is_mock:
                current_d = getattr(self.worker.ser, "current_delta", 0.0)
                
                # Máquina de estados para subir y bajar lentamente
                if current_d >= 33.5:
                    direction = -1
                elif current_d <= 8.5:
                    direction = 1

                if direction == 1:
                    if current_d < 9.0:
                        if current_d < 2.0:
                            # Arrancando desde cero (fresh start). Toma 15s llegar a 9.0.
                            self.worker.ser.target_delta = 9.0
                        else:
                            # Rebote desde el fondo (estaba estacionado en 8.0). Sube rápido a Awareness.
                            self.worker.ser.target_delta = 19.0
                    elif current_d < 19.0:
                        self.worker.ser.target_delta = 19.0
                    elif current_d < 33.0:
                        self.worker.ser.target_delta = 33.0
                    else:
                        # Llegamos a Calm Down. Nos quedamos justito arriba del umbral.
                        self.worker.ser.target_delta = 34.0
                else:
                    if current_d > 33.0:
                        # Arrancando desde Calm Down hacia abajo.
                        self.worker.ser.target_delta = 18.5
                    elif current_d > 19.0:
                        self.worker.ser.target_delta = 18.5
                    elif current_d > 9.0:
                        self.worker.ser.target_delta = 8.5
                    else:
                        # Llegamos a Reassure. Nos quedamos justito abajo del umbral.
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
                remaining = int(math.ceil(DEMO_STEP_DURATION_SEC - (time.time() - start_time)))
                self.on_tick_cb(remaining)
                time.sleep(0.2)

            self.current_policy_index = (self.current_policy_index + 1) % len(VALID_POLICIES)



# =============================================================================
# FRONTEND - INTERFAZ GRÁFICA TKINTER
# =============================================================================
class HapticDemoApp(tk.Tk):
    def __init__(self, worker: SerialWorkerThread, is_mock: bool = False):
        super().__init__()
        self.worker = worker
        self.orchestrator: Optional[DemoOrchestrator] = None

        title_suffix = " (MODO SIMULADOR / MOCK)" if is_mock else ""
        self.title(f"Pulso Háptico - Panel de Control Demo{title_suffix}")
        self.geometry("720x570")
        self.configure(bg="#222831")

        self.worker.on_telemetry_received = self.update_telemetry
        self.worker.on_log_message = self.append_log

        self.setup_ui(is_mock)

    def setup_ui(self, is_mock: bool) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        
        # Banner MOCK
        if is_mock:
            mock_banner = tk.Label(
                self, text="⚠️ EJECUTANDO EN MODO MOCK (SIN ARDUINO CONECTADO)",
                font=("Arial", 10, "bold"), bg="#ff9800", fg="black"
            )
            mock_banner.pack(fill="x")

        # Título
        title = tk.Label(
            self, text="DEMO CONTROL DE POLÍTICAS HÁPTICAS", 
            font=("Arial", 16, "bold"), bg="#222831", fg="#00ADB5"
        )
        title.pack(pady=10)

        # Panel Secuencia
        auto_frame = tk.Frame(self, bg="#393E46", bd=2, relief="groove")
        auto_frame.pack(fill="x", padx=15, pady=5)

        self.auto_var = tk.BooleanVar(value=False)
        self.auto_check = tk.Checkbutton(
            auto_frame, text=f"Modo Secuencia Automática ({DEMO_STEP_DURATION_SEC}s)", variable=self.auto_var,
            font=("Arial", 11, "bold"), bg="#393E46", fg="#EEEEEE",
            selectcolor="#222831", activebackground="#393E46", activeforeground="#00ADB5",
            command=self.toggle_auto_mode
        )
        self.auto_check.pack(side="left", padx=10, pady=10)

        self.timer_label = tk.Label(
            auto_frame, text="Timer: --s", font=("Arial", 11, "bold"), bg="#393E46", fg="#00ADB5"
        )
        self.timer_label.pack(side="right", padx=10)

        # Botones Manuales
        btn_frame = tk.LabelFrame(
            self, text=" Selección Manual de Política ", font=("Arial", 10, "bold"),
            bg="#222831", fg="#EEEEEE", bd=2, relief="groove"
        )
        btn_frame.pack(fill="x", padx=15, pady=10)

        self.buttons: Dict[str, tk.Button] = {}
        colors = {"reassure": "#2e7d32", "awareness": "#f9a825", "breath": "#1565c0", "calm_down": "#c62828"}

        for policy in VALID_POLICIES:
            btn = tk.Button(
                btn_frame, text=policy.upper(), font=("Arial", 11, "bold"),
                bg=colors[policy], fg="white", activebackground="#eeeeee",
                command=lambda p=policy: self.select_policy_manual(p)
            )
            btn.pack(side="left", expand=True, fill="x", padx=5, pady=10)
            self.buttons[policy] = btn

        stop_btn = tk.Button(
            btn_frame, text="STOP", font=("Arial", 11, "bold"),
            bg="#333333", fg="#ff4444", command=self.stop_playback
        )
        stop_btn.pack(side="right", padx=5, pady=10)

        # Monitor Telemetría
        tel_frame = tk.LabelFrame(
            self, text=" Telemetría en Tiempo Real ", font=("Arial", 10, "bold"),
            bg="#222831", fg="#EEEEEE", bd=2, relief="groove"
        )
        tel_frame.pack(fill="x", padx=15, pady=5)

        self.lbl_bpm = tk.Label(tel_frame, text="BPM: --", font=("Arial", 12), bg="#222831", fg="#EEEEEE")
        self.lbl_bpm.grid(row=0, column=0, padx=15, pady=5)

        self.lbl_smooth = tk.Label(tel_frame, text="Undefined: --", font=("Arial", 12), bg="#222831", fg="#EEEEEE")
        self.lbl_smooth.grid(row=0, column=1, padx=15, pady=5)

        self.lbl_delta = tk.Label(tel_frame, text="Undefined: --", font=("Arial", 12), bg="#222831", fg="#EEEEEE")
        self.lbl_delta.grid(row=0, column=2, padx=15, pady=5)

        self.lbl_active_policy = tk.Label(tel_frame, text="Política Activa: NINGUNA", font=("Arial", 12, "bold"), bg="#222831", fg="#00ADB5")
        self.lbl_active_policy.grid(row=1, column=0, columnspan=3, pady=5)

        # Consola Log
        log_frame = tk.LabelFrame(
            self, text=" Consola de Comunicaciones ", font=("Arial", 10, "bold"),
            bg="#222831", fg="#EEEEEE", bd=2, relief="groove"
        )
        log_frame.pack(fill="both", expand=True, padx=15, pady=10)

        self.log_text = tk.Text(log_frame, bg="#111111", fg="#00FF00", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

    def select_policy_manual(self, policy: str) -> None:
        if self.auto_var.get():
            self.auto_var.set(False)
            self.toggle_auto_mode()
        
        self.highlight_button(policy)
        self.worker.send_policy(policy)
        self.lbl_active_policy.config(text=f"Política Activa: {policy.upper()}")

    def highlight_button(self, policy: str) -> None:
        for p, btn in self.buttons.items():
            if p == policy:
                btn.config(relief="sunken", bd=4)
            else:
                btn.config(relief="raised", bd=2)

    def stop_playback(self) -> None:
        if self.auto_var.get():
            self.auto_var.set(False)
            self.toggle_auto_mode()
        self.worker.stop_motors()
        self.lbl_active_policy.config(text="Política Activa: DETENIDO")
        self.highlight_button("")

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
            self.timer_label.config(text="Timer: --s")

    def on_auto_policy_change(self, policy: str, duration: int) -> None:
        self.after(0, lambda: self._update_auto_ui(policy))

    def _update_auto_ui(self, policy: str) -> None:
        self.highlight_button(policy)
        self.lbl_active_policy.config(text=f"Política Activa (AUTO): {policy.upper()}")

    def on_auto_tick(self, remaining: int) -> None:
        self.after(0, lambda: self.timer_label.config(text=f"Timer: {remaining}s"))

    def update_telemetry(self, data: Dict[str, str]) -> None:
        def _update():
            # Solo mostrar datos si la señal es válida (baseline_samples > 0)
            signal_ok = data.get("signal_ok")
            if signal_ok == "1":
                self.lbl_bpm.config(text=f"BPM: {data.get('bpm', '--')}")
                if(data.get("phase") == "run"):
                    self.lbl_smooth.config(text=f"Baseline: {data.get('baseline_bpm', '--')}")
                    self.lbl_delta.config(text=f"Delta: {data.get('delta', '--')}")
                else:
                    self.lbl_smooth.config(text=f"Beat average: {data.get('beat_avg', '--')}")
                    self.lbl_delta.config(text=f"Samples: {data.get('baseline_samples', '--')}")
                
                # Check if we should automatically transition the policy based on mock telemetry
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
        def _append():
            self.log_text.insert(tk.END, text + "\n")
            self.log_text.see(tk.END)
        self.after(0, _append)


