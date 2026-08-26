import os
import sys

from django.apps import AppConfig


class HapticConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "haptic"
    verbose_name = "Pulso Háptico"

    def ready(self):
        # Evitar correr esto durante makemigrations/migrate/test/shell, etc.
        # Solo queremos arrancar el hilo serial cuando el server realmente
        # está sirviendo requests.
        management_commands_to_skip = {
            "makemigrations", "migrate", "collectstatic", "test",
            "shell", "createsuperuser", "dbshell", "check",
        }
        if any(cmd in sys.argv for cmd in management_commands_to_skip):
            return

        # runserver por defecto levanta un proceso "watcher" (autoreload) que
        # relanza un hijo real con RUN_MAIN=true; ready() no debería arrancar
        # el hilo serial en el watcher. Si se corre con --noreload no hay
        # watcher, así que ready() corre una sola vez y sí debe arrancarlo.
        using_runserver = "runserver" in sys.argv
        using_noreload = "--noreload" in sys.argv
        if using_runserver and not using_noreload and os.environ.get("RUN_MAIN") != "true":
            return

        from .services.controller import get_controller

        try:
            self._seed_default_calibrations()
        except Exception:
            # Las tablas pueden no existir todavía (antes del primer migrate).
            return

        get_controller().start()

    @staticmethod
    def _seed_default_calibrations():
        from . import constants
        from .models import MotorCalibration, SystemSettings

        SystemSettings.load()

        existing = set(
            MotorCalibration.objects.values_list("policy", "motor_index")
        )
        to_create = []
        for policy in constants.VALID_POLICIES:
            for motor_index in range(constants.MOTOR_COUNT):
                if (policy, motor_index) not in existing:
                    to_create.append(
                        MotorCalibration(
                            policy=policy,
                            motor_index=motor_index,
                            intensity_percent=constants.DEFAULT_MOTOR_INTENSITY_PERCENT,
                        )
                    )
        if to_create:
            MotorCalibration.objects.bulk_create(to_create)
