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


def display_received_telemetry(telemetry: Dict[str, str]) -> None:
    """Muestra en consola sólo lo importante para la maqueta."""
    phase = telemetry.get("phase", "?")
    if phase == "baseline":
        print(
            "[BPM] fase=baseline "
            f"signal_ok={telemetry.get('signal_ok')} "
            f"bpm={telemetry.get('bpm')} "
            f"beat_avg={telemetry.get('beat_avg')} "
            f"muestras={telemetry.get('baseline_samples')} "
            f"elapsed_s={telemetry.get('elapsed_s', '-')}"
        )
    elif phase == "run":
        print(
            "[BPM] fase=run "
            f"bpm={telemetry.get('bpm')} "
            f"beat_avg={telemetry.get('beat_avg')} "
            f"smooth_bpm={telemetry.get('smooth_bpm')} "
            f"baseline={telemetry.get('baseline_bpm')} "
            f"delta={telemetry.get('delta')} "
            f"policy_rx={telemetry.get('policy')} "
            f"playback={telemetry.get('playback')}"
        )


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
                    self.log(f"[RX] {telemetry}")
                   # display_received_telemetry(telemetry)

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