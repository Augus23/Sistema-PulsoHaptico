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
from demo.protocol import load_catalog
from demo.hardware import MockArduinoSerial, choose_port_interactively
from demo.hardware import SerialWorkerThread
from demo.ui import HapticDemoApp


try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("ERROR: falta instalar pyserial. Ejecutá: pip install pyserial", file=sys.stderr)
    sys.exit(1)


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