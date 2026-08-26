from django.db import models

from . import constants


class MotorCalibration(models.Model):
    """Nivel de intensidad (0-100%) de UN motor dentro de UNA política.

    Corresponde a cada slider "L1 45% / R1 45% / ..." de la pantalla de
    edición de política del mockup. Es independiente por política: el mismo
    motor puede estar calibrado distinto en "breath" que en "calm_down".
    """

    policy = models.CharField(max_length=20, choices=constants.POLICY_CHOICES)
    motor_index = models.PositiveSmallIntegerField()  # 0..5
    intensity_percent = models.FloatField(default=constants.DEFAULT_MOTOR_INTENSITY_PERCENT)

    class Meta:
        unique_together = ("policy", "motor_index")
        ordering = ["policy", "motor_index"]

    def __str__(self):
        return f"{self.policy}[{self.motor_index}]={self.intensity_percent:.0f}%"


class SystemSettings(models.Model):
    """Fila única (singleton) con el estado global del sistema."""

    global_intensity_percent = models.FloatField(default=constants.DEFAULT_GLOBAL_INTENSITY_PERCENT)
    mode = models.CharField(max_length=10, choices=constants.MODE_CHOICES, default=constants.MODE_AUTO)
    active_policy = models.CharField(max_length=20, choices=constants.POLICY_CHOICES, null=True, blank=True)

    # Última telemetría cruda conocida, guardada para que la app pueda
    # mostrar algo apenas arranca, antes de la primera respuesta en vivo.
    last_bpm = models.IntegerField(null=True, blank=True)
    last_smooth_bpm = models.IntegerField(null=True, blank=True)
    last_baseline_bpm = models.IntegerField(null=True, blank=True)
    last_signal_ok = models.BooleanField(default=False)
    last_phase = models.CharField(max_length=20, default="disconnected")
    arduino_connected = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración del sistema"
        verbose_name_plural = "Configuración del sistema"

    @classmethod
    def load(cls) -> "SystemSettings":
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
