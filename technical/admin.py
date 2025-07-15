from django.contrib import admin
from .models import (
    EnergyDelivered,
    HourlyLoad,
    FeederInterruption,
    DailyHoursOfSupply,
    FeederEnergyDaily,
    FeederEnergyMonthly,
)

@admin.register(EnergyDelivered)
class EnergyDeliveredAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'date', 'energy_mwh']
    list_filter = ['date', 'feeder']
    date_hierarchy = 'date'


@admin.register(HourlyLoad)
class HourlyLoadAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'date', 'hour', 'load_mw']
    list_filter = ['date']
    date_hierarchy = 'date'


@admin.register(FeederInterruption)
class FeederInterruptionAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'interruption_type', 'occurred_at', 'restored_at']
    list_filter = ['interruption_type', 'occurred_at']
    date_hierarchy = 'occurred_at'


@admin.register(DailyHoursOfSupply)
class DailyHoursOfSupplyAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'date', 'hours_supplied']
    list_filter = ['date']
    date_hierarchy = 'date'


@admin.register(FeederEnergyDaily)
class FeederEnergyDailyAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'date', 'energy_mwh']
    list_filter = ['feeder', 'date']
    date_hierarchy = 'date'
    search_fields = ['feeder__name']


@admin.register(FeederEnergyMonthly)
class FeederEnergyMonthlyAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'period', 'energy_mwh']
    list_filter = ['feeder', 'period']
    date_hierarchy = 'period'
    search_fields = ['feeder__name']
