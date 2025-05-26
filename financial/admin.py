from django.contrib import admin
from .models import ExpenseCategory, GLBreakdown, Expense, MonthlyRevenueBilled
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


@admin.register(MonthlyRevenueBilled)
class MonthlyRevenueBilledAdmin(admin.ModelAdmin):
    list_display = ['feeder', 'month', 'amount']
    list_filter = ['month',]


