from django.contrib import admin
from .models import Department, Role, Staff

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug',]
    search_fields = ['name']


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['title', 'department', 'slug',]
    search_fields = ['title', 'department']

@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'email', 'phone_number', 'role', 'department', 'state', 'district']
    search_fields = ['full_name', 'email', 'phone_number']
    list_filter = ['grade', 'gender', 'department']

