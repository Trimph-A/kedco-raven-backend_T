from rest_framework import serializers
from .models import Department, Role, Staff

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = '__all__'


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = '__all__'


class StaffSerializer(serializers.ModelSerializer):
    age = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = Staff
        fields = '__all__'

    def get_age(self, obj):
        return obj.age()

    def get_is_active(self, obj):
        return obj.is_active()
