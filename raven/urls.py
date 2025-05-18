"""
URL configuration for raven project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from common.views import *
from commercial.views import (
    CustomerViewSet,
    DailyEnergyDeliveredViewSet,
    DailyRevenueCollectedViewSet,
    MonthlyRevenueBilledViewSet,
    MonthlyEnergyBilledViewSet,
    MonthlyCustomerStatsViewSet,
    FeederMetricsView,

    CommercialMetricsSummaryView
)

from technical.views import (
    EnergyDeliveredViewSet,
    HourlyLoadViewSet,
    FeederInterruptionViewSet,
    DailyHoursOfSupplyViewSet,
    TechnicalMetricsView,
    TechnicalMonthlySummaryView
)

from financial.views import (
    ExpenseCategoryViewSet,
    ExpenseViewSet,
    DailyCollectionViewSet,
    MonthlyRevenueBilledViewSet,
    SalesRepresentativeViewSet,
    SalesRepPerformanceViewSet,
    FinancialSummaryView,
    SalesRepMetricsView
)
from financial.views import GLBreakdownViewSet

from regulatory.views import (
    MonthlyEnergyOfftakeViewSet,
    MonthlyRevenueRecoveryViewSet,
    MonthlyUSoASubmissionViewSet,
    MonthlyAPIStreamingRateViewSet,
    MonthlyEstimatedBillingCappingViewSet,
    MonthlyForumDecisionComplianceViewSet,
    MonthlyNERCComplaintResolutionViewSet,
)

from hr.views import DepartmentViewSet, RoleViewSet, StaffViewSet
from hr.views import HRMetricsSummaryView






router = DefaultRouter()
router.register(r'states', StateViewSet)
router.register(r'districts', BusinessDistrictViewSet)
router.register(r'substations', InjectionSubstationViewSet)
router.register(r'feeders', FeederViewSet)
router.register(r'transformers', DistributionTransformerViewSet)
router.register(r'bands', BandViewSet)

router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'daily-energy-delivered', DailyEnergyDeliveredViewSet, basename='daily-energy-delivered')
router.register(r'daily-revenue-collected', DailyRevenueCollectedViewSet, basename='daily-revenue-collected')
# router.register(r'monthly-revenue-billed', MonthlyRevenueBilledViewSet, basename='monthly-revenue-billed')
router.register(r'monthly-energy-billed', MonthlyEnergyBilledViewSet, basename='monthly-energy-billed')
router.register(r'monthly-customer-stats', MonthlyCustomerStatsViewSet, basename='monthly-customer-stats')


router.register(r'technical/energy-delivered', EnergyDeliveredViewSet, basename='energy-delivered')
router.register(r'technical/hourly-load', HourlyLoadViewSet, basename='hourly-load')
router.register(r'technical/interruptions', FeederInterruptionViewSet, basename='interruption')
router.register(r'technical/hours-of-supply', DailyHoursOfSupplyViewSet, basename='hours-of-supply')


router.register(r'financial/expense-categories', ExpenseCategoryViewSet, basename='expense-category')
router.register(r'financial/expenses', ExpenseViewSet, basename='expense')
router.register(r'financial/collections', DailyCollectionViewSet, basename='daily-collection')
router.register(r'financial/revenue-billed', MonthlyRevenueBilledViewSet, basename='monthly-revenue-billed')
router.register(r'financial/sales-reps', SalesRepresentativeViewSet, basename='sales-representative')
router.register(r'financial/sales-rep-performance', SalesRepPerformanceViewSet, basename='sales-rep-performance')
router.register(r'financial/gl-breakdowns', GLBreakdownViewSet, basename='gl-breakdown')



router.register(r'regulatory/energy-offtake', MonthlyEnergyOfftakeViewSet, basename='reg-energy-offtake')
router.register(r'regulatory/revenue-recovery', MonthlyRevenueRecoveryViewSet, basename='reg-revenue-recovery')
router.register(r'regulatory/usoa-submission', MonthlyUSoASubmissionViewSet, basename='reg-usoa')
router.register(r'regulatory/api-streaming', MonthlyAPIStreamingRateViewSet, basename='reg-api-streaming')
router.register(r'regulatory/estimated-capping', MonthlyEstimatedBillingCappingViewSet, basename='reg-capping')
router.register(r'regulatory/forum-compliance', MonthlyForumDecisionComplianceViewSet, basename='reg-forum')
router.register(r'regulatory/complaints-resolution', MonthlyNERCComplaintResolutionViewSet, basename='reg-complaints')

router.register(r'hr/departments', DepartmentViewSet, basename='hr-department')
router.register(r'hr/roles', RoleViewSet, basename='hr-role')
router.register(r'hr/staff', StaffViewSet, basename='hr-staff')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/metrics/feeder/', FeederMetricsView.as_view(), name='feeder-metrics'),
    path('api/metrics/commercial-summary/', CommercialMetricsSummaryView.as_view(), name='commercial-summary'),
    path('api/metrics/technical-summary/', TechnicalMetricsView.as_view(), name='technical-summary'),
    path('api/metrics/technical-monthly/', TechnicalMonthlySummaryView.as_view(), name='technical-monthly-summary'),
    path('api/metrics/financial-summary/', FinancialSummaryView.as_view(), name='financial-summary'),
    path('api/metrics/sales-rep-summary/', SalesRepMetricsView.as_view(), name='sales-rep-summary'),
    path('api/metrics/hr-summary/', HRMetricsSummaryView.as_view(), name='hr-summary'),

]




