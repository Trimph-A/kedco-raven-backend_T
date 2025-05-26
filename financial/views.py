from rest_framework import viewsets
from .models import *
from .serializers import *
from commercial.utils import get_filtered_feeders
from commercial.date_filters import get_date_range_from_request
from financial.metrics import (
    get_total_cost,
    get_total_revenue_billed,
    get_opex_breakdown,
    get_tariff_loss,
)
from commercial.metrics import get_total_collections
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from common.mixins import DistrictLocationFilterMixin



class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer


class ExpenseViewSet(DistrictLocationFilterMixin, viewsets.ModelViewSet):
    # queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {'district', 'gl_breakdown', 'opex_category', 'date'}

    def get_queryset(self):
        qs = Expense.objects.all()
        return self.filter_by_location(qs)

class GLBreakdownViewSet(viewsets.ModelViewSet):
    queryset = GLBreakdown.objects.all()
    serializer_class = GLBreakdownSerializer


class MonthlyRevenueBilledViewSet(viewsets.ModelViewSet):
    serializer_class = MonthlyRevenueBilledSerializer

    def get_queryset(self):
        feeders = get_filtered_feeders(self.request)
        month_from, month_to = get_date_range_from_request(self.request, 'month')

        qs = MonthlyRevenueBilled.objects.filter(feeder__in=feeders)

        if month_from and month_to:
            qs = qs.filter(month__range=(month_from, month_to))
        elif month_from:
            qs = qs.filter(month__gte=month_from)
        elif month_to:
            qs = qs.filter(month__lte=month_to)

        return qs


class FinancialSummaryView(APIView):
    def get(self, request):
        data = {
            "total_cost": round(get_total_cost(request), 2),
            "total_revenue_billed": round(get_total_revenue_billed(request), 2),
            "total_collections": round(get_total_collections(request), 2),
            "opex_breakdown": get_opex_breakdown(request),
            "tariff_loss_percentage": get_tariff_loss(request),
        }
        return Response(data)
    

