from rest_framework import serializers
from .models import *

class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = '__all__'


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = '__all__'


class DailyCollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyCollection
        fields = '__all__'


class MonthlyRevenueBilledSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonthlyRevenueBilled
        fields = '__all__'


class SalesRepresentativeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesRepresentative
        fields = '__all__'


class SalesRepPerformanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesRepPerformance
        fields = '__all__'
