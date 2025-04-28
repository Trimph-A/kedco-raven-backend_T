from rest_framework import serializers
from .models import *

class EnergyDeliveredSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnergyDelivered
        fields = '__all__'


class HourlyLoadSerializer(serializers.ModelSerializer):
    class Meta:
        model = HourlyLoad
        fields = '__all__'


class FeederInterruptionSerializer(serializers.ModelSerializer):
    duration_hours = serializers.FloatField(read_only=True)

    class Meta:
        model = FeederInterruption
        fields = '__all__'


class DailyHoursOfSupplySerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyHoursOfSupply
        fields = '__all__'
