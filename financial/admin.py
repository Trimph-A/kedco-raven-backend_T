from django.contrib import admin
from .models import ExpenseCategory, GLBreakdown, Expense, DailyCollection, MonthlyRevenueBilled, SalesRepresentative, SalesRepPerformance

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_special']
    search_fields = ['name']


@admin.register(GLBreakdown)
class GLBreakdownAdmin(admin.ModelAdmin):
    list_display = ['name',]
    search_fields = ['name',]


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['date', 'opex_category', 'credit', 'debit', 'district__name']
    list_filter = ['opex_category',]


@admin.register(DailyCollection)
class DailyCollectionAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'date', 'amount', 'collection_type', 'vendor_name']
    list_filter = ['collection_type', 'feeder__substation__district__state', 'date']


@admin.register(MonthlyRevenueBilled)
class MonthlyRevenueBilledAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'month', 'amount']
    list_filter = ['feeder__substation__district__state', 'month']


@admin.register(SalesRepresentative)
class SalesRepresentativeAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    search_fields = ['name']


@admin.register(SalesRepPerformance)
class SalesRepPerformanceAdmin(admin.ModelAdmin):
    list_display = ['sales_rep', 'month', 'current_billed', 'collections']
    list_filter = ['sales_rep', 'month']
