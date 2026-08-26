from rest_framework import serializers

from . import constants
from .models import MotorCalibration, SystemSettings


class MotorCalibrationSerializer(serializers.Serializer):
    motor_index = serializers.IntegerField(min_value=0, max_value=constants.MOTOR_COUNT - 1)
    label = serializers.CharField(read_only=True)
    intensity_percent = serializers.FloatField(min_value=0, max_value=100)

    @staticmethod
    def from_model(instance: MotorCalibration) -> dict:
        return {
            "motor_index": instance.motor_index,
            "label": constants.MOTOR_LABELS[instance.motor_index],
            "intensity_percent": instance.intensity_percent,
        }


class PolicySummarySerializer(serializers.Serializer):
    code = serializers.CharField()
    title = serializers.CharField()
    subtitle = serializers.CharField()
    description = serializers.CharField()


class PolicyDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    title = serializers.CharField()
    subtitle = serializers.CharField()
    description = serializers.CharField()
    motors = MotorCalibrationSerializer(many=True)


class MotorUpdateItemSerializer(serializers.Serializer):
    motor_index = serializers.IntegerField(min_value=0, max_value=constants.MOTOR_COUNT - 1)
    intensity_percent = serializers.FloatField(min_value=0, max_value=100)


class MotorsUpdateSerializer(serializers.Serializer):
    motors = MotorUpdateItemSerializer(many=True)


class SystemSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSettings
        fields = [
            "global_intensity_percent",
            "mode",
            "active_policy",
            "last_bpm",
            "last_smooth_bpm",
            "last_baseline_bpm",
            "last_signal_ok",
            "last_phase",
            "arduino_connected",
        ]


class SystemSettingsUpdateSerializer(serializers.Serializer):
    global_intensity_percent = serializers.FloatField(min_value=0, max_value=100, required=False)
    mode = serializers.ChoiceField(choices=constants.MODE_CHOICES, required=False)
