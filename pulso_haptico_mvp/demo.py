#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
MÓDULO DE DEMOSTRACIÓN CON FRONTEND Y MOCK - PULSO HÁPTICO
===============================================================================
Descripción:
    Aplicación gráfica (Tkinter) para demostración del sistema háptico.
    Permite cambiar de política manualmente mediante botones en la interfaz 
    o activar un modo de secuencia automática cada 30 segundos.

    Incluye modo MOCK (--mock) para probar todo el software y la interfaz
    sin necesidad de conectar el Arduino Nano ni el sensor.

Uso:
    Con Hardware:   python demo.py --port COM5 --catalog patterns
    Sin Hardware:   python demo.py --mock --catalog patterns
===============================================================================
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("ERROR: falta instalar pyserial. Ejecutá: pip install pyserial", file=sys.stderr)
    sys.exit(1)


# =============================================================================
# CONSTANTES Y PROTOCOLO
# =============================================================================
POLICY_TO_CODE = {
    "reassure": 1,
    "awareness": 2,
    "breath": 3,
    "calm_down": 4,
}

TRANSITION_TO_CODE = {
    "instant": 0,
    "ramp_up": 1,
    "hold": 2,
    "ramp_down": 3,
    "pause": 4,
}

VALID_POLICIES = ["reassure", "awareness", "breath", "calm_down"]
DEMO_STEP_DURATION_SEC = 15.0


# =============================================================================
# ESTRUCTURAS DE DATOS Y UTILIDADES DE PATRÓN
# =============================================================================
@dataclass
class EffectivePattern:
    policy: str
    pattern_id: str
    customized: bool
    repeat_count: int
    cooldown_ms: int
    commands: List[str]
    human_steps: List[Dict[str, Any]]


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def channels_to_mask(channels: List[int]) -> int:
    mask = 0
    for i, active in enumerate(channels):
        if active:
            mask |= (1 << i)
    return mask


def load_catalog(catalog_dir: Path) -> Dict[str, Dict[str, Any]]:
    if not catalog_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta de catálogo: {catalog_dir}")

    catalog: Dict[str, Dict[str, Any]] = {}
    for path in sorted(catalog_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as f:
            pattern = json.load(f)
        policy = pattern["context"]["policy"]
        catalog[policy] = pattern
    return catalog


def build_effective_pattern(pattern: Dict[str, Any]) -> EffectivePattern:
    policy = pattern["context"]["policy"]
    adjustable = pattern["adjustable_params"]
    
    base_intensity = float(adjustable["intensity_scale"]["default"])
    base_duration = float(adjustable["duration_scale"]["default"])
    repeat_count = int(pattern["playback"]["repeat_count"])
    cooldown_ms = int(pattern["playback"]["cooldown_ms"])
    policy_code = POLICY_TO_CODE[policy]

    commands: List[str] = [
        f"PATTERN,{policy_code},0,{repeat_count},{cooldown_ms},{len(pattern['steps'])}"
    ]
    human_steps: List[Dict[str, Any]] = []

    for step in pattern["steps"]:
        duration_ms = max(1, int(round(int(step["duration_ms"]) * base_duration)))
        pwm = int(round(float(step["intensity"]) * base_intensity * 255.0))
        pwm = int(clamp(pwm, 0, 255))
        mask = channels_to_mask(step["channels"])
        transition_code = TRANSITION_TO_CODE[step["transition"]]
        
        commands.append(f"STEP,{duration_ms},{mask},{pwm},{transition_code}")
        human_steps.append({
            "duration_ms": duration_ms,
            "mask": mask,
            "pwm": pwm,
            "transition": step["transition"],
            "channels": step["channels"],
        })

    commands.append("END")

    return EffectivePattern(
        policy=policy,
        pattern_id=pattern["pattern_id"],
        customized=False,
        repeat_count=repeat_count,
        cooldown_ms=cooldown_ms,
        commands=commands,
        human_steps=human_steps
    )


def parse_telemetry_line(line: str) -> Optional[Dict[str, str]]:
    if not line.startswith("TEL,"):
        return None
    result: Dict[str, str] = {}
    for part in line[4:].split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip()] = v.strip()
    return result


# =============================================================================
# SIMULADOR DE ARDUINO (MOCK SERIAL)
# =============================================================================
class MockArduinoSerial:
    """
    Simula una interfaz de objeto pySerial en memoria para probar
    el programa sin necesidad de conectar hardware real.
    """
    def __init__(self):
        self.read_buffer: List[str] = [
            "EVT,boot,device=stress_detector_amped_haptic_mvp_MOCK\n",
            "EVT,info,pulse_sensor=SIMULATOR,motors=6_PWM\n"
        ]
        self.lock = threading.Lock()
        self.running = True
        self.baseline_bpm = 70
        
        # Hilo de generación de telemetría falsa
        self.telemetry_thread = threading.Thread(target=self._generate_telemetry, daemon=True)
        self.telemetry_thread.start()

    def _generate_telemetry(self):
        t = 0
        while self.running:
            time.sleep(1.0)
            t += 1
            # Oscilación simulada de BPM entre 65 y 105
            simulated_bpm = int(75 + 20 * math.sin(t / 5.0))
            smooth_bpm = int(73 + 18 * math.sin((t - 2) / 5.0))
            delta = smooth_bpm - self.baseline_bpm

            line = (
                f"TEL,phase=run,raw=512,smooth_signal=510.0,amp=150,signal_ok=1,"
                f"bpm={simulated_bpm}.0,beat_avg={simulated_bpm},smooth_bpm={smooth_bpm},"
                f"baseline_bpm={self.baseline_bpm},delta={delta},"
                f"level=regulacion_estable,policy=reassure,policy_code=1,playback=0\n"
            )
            
            with self.lock:
                self.read_buffer.append(line)

    def readline(self) -> bytes:
        while self.running:
            with self.lock:
                if self.read_buffer:
                    return self.read_buffer.pop(0).encode("utf-8")
            time.sleep(0.05)
        return b""

    def write(self, data: bytes) -> int:
        cmd = data.decode("ascii", errors="ignore").strip()
        
        # Respuestas simuladas del protocolo
        with self.lock:
            if cmd == "PING":
                self.read_buffer.append("ACK,PONG\n")
            elif cmd == "STOP":
                self.read_buffer.append("ACK,STOPPED\n")
            elif cmd.startswith("PATTERN,"):
                parts = cmd.split(",")
                self.read_buffer.append(f"ACK,PATTERN_HEADER,policy_code={parts[1]},custom={parts[2]},steps={parts[5]}\n")
            elif cmd.startswith("STEP,"):
                self.read_buffer.append("ACK,STEP,OK\n")
            elif cmd == "END":
                self.read_buffer.append("ACK,PATTERN_LOADED,status=OK\n")
                self.read_buffer.append("EVT,playback_started\n")

        return len(data)

    def flush(self):
        pass

    def close(self):
        self.running = False


# =============================================================================
# COMUNICACIÓN SERIAL (WORKER THREAD)
# =============================================================================
class SerialWorkerThread(threading.Thread):
    def __init__(self, ser: Any, catalog: Dict[str, Dict[str, Any]]):
        super().__init__(daemon=True)
        self.ser = ser
        self.catalog = catalog
        self.running = True
        
        self.on_telemetry_received: Optional[Callable[[Dict[str, str]], None]] = None
        self.on_log_message: Optional[Callable[[str], None]] = None

    def log(self, message: str) -> None:
        print(message)
        if self.on_log_message:
            self.on_log_message(message)

    def run(self) -> None:
        while self.running:
            try:
                raw = self.ser.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                if line.startswith(("EVT,", "ACK,", "ERR,")):
                    self.log(f"[HARDWARE] {line}")
                    continue

                telemetry = parse_telemetry_line(line)
                if telemetry and self.on_telemetry_received:
                    self.on_telemetry_received(telemetry)

            except Exception as e:
                self.log(f"[ERROR READ] {e}")
                break

    def send_policy(self, policy: str) -> None:
        if policy not in self.catalog:
            self.log(f"[ERROR] Política '{policy}' no encontrada en catálogo.")
            return

        effective = build_effective_pattern(self.catalog[policy])
        self.log(f"[TX] Enviando Política: {effective.policy.upper()} ({effective.pattern_id})")

        for command in effective.commands:
            self.ser.write((command + "\n").encode("ascii"))
            self.ser.flush()
            time.sleep(0.015)

    def stop_motors(self) -> None:
        try:
            self.ser.write(b"STOP\n")
            self.ser.flush()
            self.log("[TX] Comando STOP enviado")
        except Exception as e:
            self.log(f"[ERROR] Fallo al detener: {e}")

    def stop(self) -> None:
        self.running = False
        self.stop_motors()
        if hasattr(self.ser, "close"):
            self.ser.close()


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

    def start_demo(self) -> None:
        if not self.running:
            self.running = True
            super().__init__(daemon=True)
            self.start()

    def stop_demo(self) -> None:
        self.running = False

    def run(self) -> None:
        while self.running:
            policy = VALID_POLICIES[self.current_policy_index]
            self.worker.send_policy(policy)
            self.on_change_cb(policy, int(DEMO_STEP_DURATION_SEC))

            start_time = time.time()
            while time.time() - start_time < DEMO_STEP_DURATION_SEC:
                if not self.running:
                    return
                remaining = int(DEMO_STEP_DURATION_SEC - (time.time() - start_time))
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
            auto_frame, text="Modo Secuencia Automática (30s)", variable=self.auto_var,
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

        self.lbl_smooth = tk.Label(tel_frame, text="Smooth BPM: --", font=("Arial", 12), bg="#222831", fg="#EEEEEE")
        self.lbl_smooth.grid(row=0, column=1, padx=15, pady=5)

        self.lbl_delta = tk.Label(tel_frame, text="Delta: --", font=("Arial", 12), bg="#222831", fg="#EEEEEE")
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
            if data.get("phase") == "run":
                self.lbl_bpm.config(text=f"BPM: {data.get('bpm', '--')}")
                self.lbl_smooth.config(text=f"Smooth BPM: {data.get('smooth_bpm', '--')}")
                self.lbl_delta.config(text=f"Delta: {data.get('delta', '--')}")
        self.after(0, _update)

    def append_log(self, text: str) -> None:
        def _append():
            self.log_text.insert(tk.END, text + "\n")
            self.log_text.see(tk.END)
        self.after(0, _append)


# =============================================================================
# MAIN Y DETECCIÓN
# =============================================================================
def choose_port_interactively() -> Optional[str]:
    ports = list(list_ports.comports())
    if not ports:
        return None
    if len(ports) == 1:
        return ports[0].device
    print("Puertos disponibles:")
    for i, p in enumerate(ports, 1):
        print(f"  {i}. {p.device} - {p.description}")
    idx = int(input("Seleccione el puerto (número): ")) - 1
    return ports[idx].device


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo de Control Háptico (Soporta Hardware o Mock).")
    parser.add_argument("--port", help="Puerto Serial (ej. COM5, /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="Velocidad de transmisión")
    parser.add_argument("--catalog", default="patterns", help="Ruta de la carpeta de patrones JSON")
    parser.add_argument("--mock", action="store_true", help="Ejecuta en modo simulación sin hardware")
    args = parser.parse_args()

    try:
        catalog = load_catalog(Path(args.catalog))
    except Exception as e:
        print(f"[ERROR] Falló la carga del catálogo: {e}")
        return 1

    ser_instance: Any = None

    if args.mock:
        print("[MOCK] Inicializando simulador de hardware...")
        ser_instance = MockArduinoSerial()
    else:
        port = args.port or choose_port_interactively()
        if not port:
            print("[ERROR] No se seleccionó puerto. Si no tienes hardware, ejecuta con --mock")
            return 1

        try:
            ser_instance = serial.Serial(port=port, baudrate=args.baud, timeout=1.0)
            time.sleep(2.0)
            ser_instance.reset_input_buffer()
        except serial.SerialException as e:
            print(f"[ERROR] No se pudo abrir puerto {port}: {e}")
            return 1

    worker = SerialWorkerThread(ser_instance, catalog)
    worker.start()

    app = HapticDemoApp(worker, is_mock=args.mock)

    def on_closing():
        if app.orchestrator:
            app.orchestrator.stop_demo()
        worker.stop()
        app.destroy()

    app.protocol("WM_DELETE_WINDOW", on_closing)
    app.mainloop()

    return 0


if __name__ == "__main__":
    sys.exit(main())