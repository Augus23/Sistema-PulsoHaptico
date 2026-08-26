from rest_framework.response import Response
from rest_framework.views import APIView

from . import constants
from .models import MotorCalibration, SystemSettings
from .serializers import (
    MotorCalibrationSerializer,
    MotorsUpdateSerializer,
    PolicyDetailSerializer,
    PolicySummarySerializer,
    SystemSettingsSerializer,
    SystemSettingsUpdateSerializer,
)
from .services import pattern_engine
from .services.controller import get_controller


def _policy_or_404_codes():
    return constants.VALID_POLICIES


class PolicyListView(APIView):
    """GET /api/policies/  -> las 4 tarjetas de la pantalla principal."""

    def get(self, request):
        data = []
        for code in constants.VALID_POLICIES:
            title, subtitle = constants.POLICY_TITLES[code]
            data.append(
                {
                    "code": code,
                    "title": title,
                    "subtitle": subtitle,
                    "description": pattern_engine.get_policy_description(code),
                }
            )
        serializer = PolicySummarySerializer(data, many=True)
        return Response(serializer.data)


class PolicyDetailView(APIView):
    """GET /api/policies/<code>/ -> detalle + calibración de los 6 motores."""

    def get(self, request, code):
        if code not in constants.VALID_POLICIES:
            return Response({"detail": "Política inválida"}, status=404)

        title, subtitle = constants.POLICY_TITLES[code]

        existing = {
            row.motor_index: row
            for row in MotorCalibration.objects.filter(policy=code)
        }
        motors = []
        for i in range(constants.MOTOR_COUNT):
            row = existing.get(i)
            if row is None:
                motors.append(
                    {
                        "motor_index": i,
                        "label": constants.MOTOR_LABELS[i],
                        "intensity_percent": constants.DEFAULT_MOTOR_INTENSITY_PERCENT,
                    }
                )
            else:
                motors.append(MotorCalibrationSerializer.from_model(row))

        data = {
            "code": code,
            "title": title,
            "subtitle": subtitle,
            "description": pattern_engine.get_policy_description(code),
            "motors": motors,
        }
        serializer = PolicyDetailSerializer(data)
        return Response(serializer.data)


class PolicyMotorsUpdateView(APIView):
    """PUT /api/policies/<code>/motors/ -> botón 'Guardar Cambios del Patrón'."""

    def put(self, request, code):
        if code not in constants.VALID_POLICIES:
            return Response({"detail": "Política inválida"}, status=404)

        serializer = MotorsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        for item in serializer.validated_data["motors"]:
            MotorCalibration.objects.update_or_create(
                policy=code,
                motor_index=item["motor_index"],
                defaults={"intensity_percent": item["intensity_percent"]},
            )

        return PolicyDetailView().get(request, code)


class PolicyActivateView(APIView):
    """POST /api/policies/<code>/activate/ -> disparo manual inmediato."""

    def post(self, request, code):
        if code not in constants.VALID_POLICIES:
            return Response({"detail": "Política inválida"}, status=404)

        get_controller().send_policy(code)

        settings_row = SystemSettings.load()
        settings_row.active_policy = code
        settings_row.save()

        return Response({"sent": code})


class StatusView(APIView):
    """GET /api/status/ -> estado global (bpm, conexión, modo, intensidad global)."""

    def get(self, request):
        settings_row = SystemSettings.load()
        return Response(SystemSettingsSerializer(settings_row).data)

    def put(self, request):
        serializer = SystemSettingsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        settings_row = SystemSettings.load()
        for field, value in serializer.validated_data.items():
            setattr(settings_row, field, value)
        settings_row.save()

        return Response(SystemSettingsSerializer(settings_row).data)


class StopView(APIView):
    """POST /api/stop/ -> apaga los motores inmediatamente."""

    def post(self, request):
        get_controller().send_stop()
        return Response({"stopped": True})
