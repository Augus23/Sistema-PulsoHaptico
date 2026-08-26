# El admin de Django no está habilitado en INSTALLED_APPS de este MVP
# (no hace falta contrib.admin para esta app). Si en el futuro se agrega
# "django.contrib.admin" a INSTALLED_APPS, descomentar lo siguiente:
#
# from django.contrib import admin
# from .models import MotorCalibration, SystemSettings
#
# admin.site.register(MotorCalibration)
# admin.site.register(SystemSettings)
