"""Conexión de bajo nivel con el Arduino por USB serial.

Incluye un modo "mock" (sin hardware real) para poder desarrollar y probar
el backend y la app mobile sin tener el Arduino conectado. Se activa con
la variable de entorno PULSO_MOCK_ARDUINO=1.
"""

from __future__ import annotations

import math
import random
import time
from typing import Optional


class RealSerialLink:
    """Wrapper fino sobre pyserial."""

    def __init__(self, port: str, baudrate: int):
        import serial  # import acá para no romper si no está instalado en mock mode

        self.port = port
        self.baudrate = baudrate
        self._serial = serial.Serial(port=port, baudrate=baudrate, timeout=1.0, write_timeout=1.0)
        time.sleep(2.0)  # el Arduino se resetea al abrir el puerto
        self._serial.reset_input_buffer()

    @property
    def is_open(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def readline(self) -> Optional[str]:
        raw = self._serial.readline()
        if not raw:
            return None
        return raw.decode("utf-8", errors="replace").strip()

    def write_line(self, line: str) -> None:
        self._serial.write((line + "\n").encode("ascii"))
        self._serial.flush()

    def close(self) -> None:
        try:
            self._serial.close()
        except Exception:
            pass


class MockSerialLink:
    """Simula telemetría de Arduino sin hardware, para desarrollo.

    Genera un baseline fijo y un smooth_bpm que va y viene senoidalmente
    para poder ver, en la app, cómo cambian las políticas automáticamente.
    """

    def __init__(self):
        self._start_time = time.time()
        self._baseline_bpm = 70
        self._last_send = 0.0

    @property
    def is_open(self) -> bool:
        return True

    def readline(self) -> Optional[str]:
        # Simula ~1 línea de telemetría por segundo, como el firmware real.
        now = time.time()
        if now - self._last_send < 1.0:
            time.sleep(0.05)
            return None
        self._last_send = now

        elapsed = now - self._start_time
        # Oscila el bpm suavizado para recorrer las 4 políticas con el tiempo.
        oscillation = 25 + 25 * math.sin(elapsed / 20.0)
        smooth_bpm = int(self._baseline_bpm + oscillation + random.uniform(-1, 1))
        bpm = smooth_bpm + random.randint(-2, 2)

        return (
            f"TEL,phase=run,signal_ok=1,bpm={bpm},beat_avg={bpm},"
            f"smooth_bpm={smooth_bpm},baseline_bpm={self._baseline_bpm},"
            f"playback=0,active_policy_code=0"
        )

    def write_line(self, line: str) -> None:
        # No hacemos nada real; podría loguearse si hace falta debug.
        pass

    def close(self) -> None:
        pass
