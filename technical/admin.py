from django.contrib import admin
from .models import EnergyDelivered, HourlyLoad, FeederInterruption, DailyHoursOfSupply

@admin.register(EnergyDelivered)
class EnergyDeliveredAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'date', 'energy_mwh']
    list_filter = ['feeder__substation__district__state', 'date']


@admin.register(HourlyLoad)
class HourlyLoadAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'date', 'hour', 'load_mw']
    list_filter = ['feeder__substation__district__state', 'date']


@admin.register(FeederInterruption)
class FeederInterruptionAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'interruption_type', 'occurred_at', 'restored_at']
    list_filter = ['feeder__substation__district__state', 'interruption_type', 'occurred_at']


@admin.register(DailyHoursOfSupply)
class DailyHoursOfSupplyAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'date', 'hours_supplied']
    list_filter = ['feeder__substation__district__state', 'date']
