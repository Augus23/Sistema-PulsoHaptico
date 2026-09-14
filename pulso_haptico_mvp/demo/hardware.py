from typing import Optional, Any, Dict, List, Callable
from serial import Serial
import threading
import math
import time
import serial.tools.list_ports as list_ports
from demo.protocol import parse_telemetry_line, build_effective_pattern


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
        self.current_delta = 0.0
        self._target_delta = 0.0
        self.delta_step_value = 0.5
        
        # Hilo de generación de telemetría falsa
        self.telemetry_thread = threading.Thread(target=self._generate_telemetry, daemon=True)
        self.telemetry_thread.start()

    @property
    def target_delta(self) -> float:
        return self._target_delta

    @target_delta.setter
    def target_delta(self, value: float) -> None:
        self._target_delta = value
        # Calculamos el paso lineal para que llegue al objetivo un poco antes (13.5s)
        # Esto compensa los delays del time.sleep y asegura que cruce el umbral a tiempo
        self.delta_step_value = abs(self._target_delta - self.current_delta) / 13.5
        if self.delta_step_value < 0.5:
            self.delta_step_value = 0.5

    def _generate_telemetry(self):
        t = 0
        while self.running:
            time.sleep(1.0)
            t += 1
            
            with self.lock:
                if self.current_delta < self._target_delta:
                    self.current_delta = min(self._target_delta, self.current_delta + self.delta_step_value)
                elif self.current_delta > self._target_delta:
                    self.current_delta = max(self._target_delta, self.current_delta - self.delta_step_value)
                delta = int(self.current_delta)

            smooth_bpm = self.baseline_bpm + delta
            # Oscilación simulada leve de BPM
            simulated_bpm = smooth_bpm + int(3 * math.sin(t))

            # Clasificación de acuerdo a reglas del sketch de Arduino
            if delta >= 33:
                pol = "calm_down"
                pol_code = 4
                lvl = "activacion_alta"
            elif delta >= 19:
                pol = "breath"
                pol_code = 3
                lvl = "activacion_moderada"
            elif delta >= 9:
                pol = "awareness"
                pol_code = 2
                lvl = "activacion_leve"
            else:
                pol = "reassure"
                pol_code = 1
                lvl = "regulacion_estable"

            line = (
                f"TEL,phase=run,raw=512,smooth_signal=510.0,amp=150,signal_ok=1,"
                f"bpm={simulated_bpm}.0,beat_avg={simulated_bpm},smooth_bpm={smooth_bpm},"
                f"baseline_bpm={self.baseline_bpm},delta={delta},"
                f"level={lvl},policy={pol},policy_code={pol_code},playback=0\n"
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