from typing import Optional, Any, Dict, List, Callable
import threading
import time

try:
    from serial import Serial
    import serial.tools.list_ports as list_ports
except ImportError:  # pragma: no cover - solo para mock/demo sin hardware
    Serial = Any  # type: ignore[misc]
    list_ports = None

from demo.config import POLICY_TO_CODE, BPM_CONFIG
from demo.protocol import parse_telemetry_line, build_effective_pattern

MOCK_BASELINE_BPM = 68


def choose_port_interactively() -> Optional[str]:
    if list_ports is None:
        return None
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
    POLICY_TO_DELTA = {"awareness": 12.0, "reassure": 4.0, "breath": 25.0, "calm_down": 38.0}

    def __init__(self):
        self.read_buffer: List[str] = [
            "EVT,boot,device=stress_detector_amped_haptic_mvp_MOCK\n",
            "EVT,info,pulse_sensor=SIMULATOR,motors=6_PWM\n"
        ]
        self.lock = threading.Lock()
        self.running = True
        self.baseline_bpm = 70
        self.baseline_count = 0
        self.playback_active = 0
        self.signal_ok = False
        
        self.telemetry_thread = threading.Thread(target=self._generate_telemetry, daemon=True)
        self.telemetry_thread.start()

    def _queue_boot_telemetry(self) -> None:
        self.read_buffer.append(
            "TEL,phase=baseline,raw=512,smooth_signal=510.0,amp=0,signal_ok=0,"
            "bpm=0,beat_avg=0,baseline_samples=0,waiting_for_valid_signal=1,policy=none,policy_code=0\n"
        )

    def _generate_telemetry(self):
        while self.running:
            time.sleep(1.0)
            line = (
                f"TEL,phase=run,raw=512,smooth_signal=510.0,amp=150,signal_ok=1,"
                f"bpm={self.baseline_bpm}.0,beat_avg={self.baseline_bpm},smooth_bpm={self.baseline_bpm},"
                f"baseline_bpm={self.baseline_bpm},delta=0,"
                f"level=activacion_leve,policy=awareness,policy_code=2,playback={self.playback_active}\n"
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

        with self.lock:
            if cmd == "PING":
                self.read_buffer.append("ACK,PONG\n")
            elif cmd == "STOP":
                self.read_buffer.append("ACK,STOPPED\n")
                self.playback_active = 0
                self.current_policy = None
                self.signal_ok = False
                self.current_delta = 0.0
                self.target_delta = 0.0
                self.baseline_count = 0
            elif cmd.startswith("PATTERN,"):
                parts = cmd.split(",")
                self.read_buffer.append(
                    f"ACK,PATTERN_HEADER,policy_code={parts[1]},custom={parts[2]},steps={parts[5]}\n"
                )
            elif cmd.startswith("STEP,"):
                self.read_buffer.append("ACK,STEP,OK\n")
            elif cmd == "END":
                self.read_buffer.append("ACK,PATTERN_LOADED,status=OK\n")
                self.read_buffer.append("EVT,playback_started\n")
                self.playback_active = 1

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

        if hasattr(self.ser, "set_policy"):
            self.ser.set_policy(policy)
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