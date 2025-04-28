from django.contrib import admin
from .models import Customer, DailyEnergyDelivered, DailyRevenueCollected, MonthlyEnergyBilled, MonthlyRevenueBilled, MonthlyCustomerStats

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'metering_type', 'band', 'transformer']
    search_fields = ['name']
    list_filter = ['category', 'metering_type', 'band']


@admin.register(DailyEnergyDelivered)
class DailyEnergyDeliveredAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'date', 'energy_mwh']
    list_filter = ['feeder__substation__district__state', 'date']


@admin.register(DailyRevenueCollected)
class DailyRevenueCollectedAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'date', 'amount']
    list_filter = ['feeder__substation__district__state', 'date']


@admin.register(MonthlyEnergyBilled)
class MonthlyEnergyBilledAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'month', 'energy_mwh']
    list_filter = ['feeder__substation__district__state', 'month']


@admin.register(MonthlyRevenueBilled)
class MonthlyRevenueBilledAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'month', 'amount']
    list_filter = ['feeder__substation__district__state', 'month']


@admin.register(MonthlyCustomerStats)
class MonthlyCustomerStatsAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'month', 'customers_billed', 'customer_response_count']
    list_filter = ['feeder__substation__district__state', 'month']
