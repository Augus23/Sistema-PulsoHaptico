"""Controlador central de Pulso Háptico.

Corre en un hilo de background dentro del proceso de Django. Es el único
lugar que:
  - lee telemetría cruda (bpm/smooth_bpm/baseline_bpm) del Arduino,
  - decide, en modo automático, qué política corresponde según el BPM,
  - traduce esa política a comandos seriales usando la calibración por
    motor guardada en la base de datos,
  - se los manda al Arduino.

La app mobile (o cualquier cliente REST) sólo lee/escribe estado a través
de las vistas de haptic/views.py; nunca habla serial directamente.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from django.conf import settings
from django.db import close_old_connections

from .. import constants
from . import pattern_engine
from .serial_link import MockSerialLink, RealSerialLink


class HapticController:
    def __init__(self):
        self._lock = threading.RLock()
        self._link = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        self._last_sent_policy: Optional[str] = None
        self._last_sent_time: float = 0.0

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            self._running = False

    # ------------------------------------------------------------------
    # Conexión serial
    # ------------------------------------------------------------------
    def _open_link(self):
        if settings.PULSO_MOCK_ARDUINO:
            print("[haptic] Modo MOCK activo: simulando telemetría sin Arduino real.")
            return MockSerialLink()

        port = settings.PULSO_SERIAL_PORT
        if not port:
            port = self._autodetect_port()

        if not port:
            print("[haptic] No se encontró puerto serial. Reintentando en unos segundos...")
            return None

        try:
            link = RealSerialLink(port=port, baudrate=settings.PULSO_BAUDRATE)
            print(f"[haptic] Conectado a Arduino en {port} @ {settings.PULSO_BAUDRATE} baudios.")
            return link
        except Exception as exc:
            print(f"[haptic] No se pudo abrir el puerto {port}: {exc}")
            return None

    @staticmethod
    def _autodetect_port() -> Optional[str]:
        try:
            from serial.tools import list_ports
        except ImportError:
            return None
        ports = list(list_ports.comports())
        return ports[0].device if ports else None

    # ------------------------------------------------------------------
    # Loop principal (corre en el hilo de background)
    # ------------------------------------------------------------------
    def _run_loop(self):
        while self._running:
            if self._link is None:
                self._link = self._open_link()
                self._set_connected(self._link is not None)
                if self._link is None:
                    time.sleep(3.0)
                    continue

            try:
                line = self._link.readline()
            except Exception as exc:
                print(f"[haptic] Error leyendo serial: {exc}. Reconectando...")
                self._teardown_link()
                continue

            if not line:
                continue

            close_old_connections()
            self._handle_incoming_line(line)

    def _teardown_link(self):
        if self._link is not None:
            try:
                self._link.close()
            except Exception:
                pass
        self._link = None
        self._set_connected(False)
        time.sleep(2.0)

    def _set_connected(self, connected: bool):
        from ..models import SystemSettings

        settings_row = SystemSettings.load()
        settings_row.arduino_connected = connected
        if not connected:
            settings_row.last_phase = "disconnected"
        settings_row.save()

    # ------------------------------------------------------------------
    # Parseo de líneas entrantes
    # ------------------------------------------------------------------
    def _handle_incoming_line(self, line: str):
        if line.startswith("TEL,"):
            self._handle_telemetry(line)
        elif line.startswith(("EVT,", "ACK,", "ERR,")):
            print(f"[arduino] {line}")
        # Otras líneas (ruido/basura durante boot) se ignoran.

    def _handle_telemetry(self, line: str):
        from ..models import SystemSettings

        fields = {}
        for part in line[len("TEL,"):].split(","):
            if "=" in part:
                key, value = part.split("=", 1)
                fields[key] = value

        settings_row = SystemSettings.load()
        settings_row.arduino_connected = True
        settings_row.last_phase = fields.get("phase", settings_row.last_phase)
        settings_row.last_signal_ok = fields.get("signal_ok") == "1"

        if "bpm" in fields:
            settings_row.last_bpm = _safe_int(fields.get("bpm"))
        if "smooth_bpm" in fields:
            settings_row.last_smooth_bpm = _safe_int(fields.get("smooth_bpm"))
        if "baseline_bpm" in fields:
            settings_row.last_baseline_bpm = _safe_int(fields.get("baseline_bpm"))

        settings_row.save()

        if settings_row.mode != constants.MODE_AUTO:
            return
        if settings_row.last_phase != "run" or not settings_row.last_signal_ok:
            return
        if settings_row.last_smooth_bpm is None or settings_row.last_baseline_bpm is None:
            return

        delta = settings_row.last_smooth_bpm - settings_row.last_baseline_bpm
        policy = pattern_engine.decide_policy_from_delta(delta)
        self._maybe_send_policy(policy, settings_row)

    def _maybe_send_policy(self, policy: str, settings_row) -> None:
        now = time.time()
        min_gap = settings.PULSO_MIN_SECONDS_BETWEEN_SAME_POLICY

        same_policy_recent = (
            policy == self._last_sent_policy and (now - self._last_sent_time) < min_gap
        )
        if same_policy_recent:
            return

        self.send_policy(policy)
        settings_row.active_policy = policy
        settings_row.save()

    # ------------------------------------------------------------------
    # Envío de patrones (llamado desde el loop automático o manualmente
    # desde las vistas REST, por eso está protegido con lock)
    # ------------------------------------------------------------------
    def send_policy(self, policy: str) -> None:
        from ..models import MotorCalibration

        with self._lock:
            if self._link is None:
                print("[haptic] No hay Arduino conectado; no se envía el patrón.")
                return

            calibrations = {
                row.motor_index: row.intensity_percent
                for row in MotorCalibration.objects.filter(policy=policy)
            }
            motor_percents = [
                calibrations.get(i, constants.DEFAULT_MOTOR_INTENSITY_PERCENT)
                for i in range(constants.MOTOR_COUNT)
            ]

            from ..models import SystemSettings
            global_percent = SystemSettings.load().global_intensity_percent

            commands = pattern_engine.build_serial_commands(
                policy=policy,
                motor_intensity_percent=motor_percents,
                global_intensity_percent=global_percent,
            )

            print(f"[haptic] Enviando política '{policy}' ({len(commands)} líneas).")
            for command in commands:
                try:
                    self._link.write_line(command)
                except Exception as exc:
                    print(f"[haptic] Error escribiendo en serial: {exc}")
                    self._teardown_link()
                    return
                time.sleep(0.015)

            self._last_sent_policy = policy
            self._last_sent_time = time.time()

    def send_stop(self) -> None:
        with self._lock:
            if self._link is None:
                return
            try:
                self._link.write_line("STOP")
            except Exception:
                pass


def _safe_int(value) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


_controller_singleton: Optional[HapticController] = None
_singleton_lock = threading.Lock()


def get_controller() -> HapticController:
    global _controller_singleton
    with _singleton_lock:
        if _controller_singleton is None:
            _controller_singleton = HapticController()
        return _controller_singleton
