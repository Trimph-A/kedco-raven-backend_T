from rest_framework import serializers
from .models import *
from common.serializers import FeederSerializer


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'


class DailyEnergyDeliveredSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyEnergyDelivered
        fields = '__all__'


class DailyRevenueCollectedSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyRevenueCollected
        fields = '__all__'


class MonthlyRevenueBilledSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonthlyRevenueBilled
        fields = '__all__'


class MonthlyEnergyBilledSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonthlyEnergyBilled
        fields = '__all__'


class MonthlyCustomerStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonthlyCustomerStats
        fields = '__all__'
