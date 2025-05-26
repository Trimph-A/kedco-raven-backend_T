from rest_framework import viewsets
from .models import *
from .serializers import *
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, F, FloatField, ExpressionWrapper, Q
from common.models import Feeder, State
from datetime import datetime
from .utils import get_filtered_feeders
from commercial.date_filters import get_date_range_from_request
from commercial.mixins import FeederFilteredQuerySetMixin
from commercial.utils import get_filtered_customers
from commercial.metrics import calculate_derived_metrics, get_sales_rep_performance_summary
from rest_framework.decorators import api_view
from decimal import Decimal, InvalidOperation
from technical.models import EnergyDelivered
from financial.models import MonthlyRevenueBilled
from commercial.models import DailyCollection
from django.utils.dateparse import parse_date
from datetime import date
from dateutil.relativedelta import relativedelta


class CustomerViewSet(viewsets.ViewSet):
    """
    Custom ViewSet to return either customer details or just counts
    """

    def list(self, request):
        customers = get_filtered_customers(request)

        # Show full data only if explicitly asked for
        if request.GET.get("details") == "true":
            serializer = CustomerSerializer(customers, many=True)
            return Response(serializer.data)
        else:
            count = customers.count()
            return Response({"count": count})


class DailyEnergyDeliveredViewSet(FeederFilteredQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = DailyEnergyDeliveredSerializer

    def get_queryset(self):
        queryset = DailyEnergyDelivered.objects.all()
        queryset = self.filter_by_location(queryset)
        date_from, date_to = get_date_range_from_request(self.request, 'date')

        if date_from and date_to:
            queryset = queryset.filter(date__range=(date_from, date_to))
        elif date_from:
            queryset = queryset.filter(date__gte=date_from)
        elif date_to:
            queryset = queryset.filter(date__lte=date_to)

        return queryset


class DailyRevenueCollectedViewSet(FeederFilteredQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = DailyRevenueCollectedSerializer

    def get_queryset(self):
        queryset = DailyRevenueCollected.objects.all()
        queryset = self.filter_by_location(queryset)
        date_from, date_to = get_date_range_from_request(self.request, 'date')

        if date_from and date_to:
            queryset = queryset.filter(date__range=(date_from, date_to))
        elif date_from:
            queryset = queryset.filter(date__gte=date_from)
        elif date_to:
            queryset = queryset.filter(date__lte=date_to)

        return queryset


class MonthlyRevenueBilledViewSet(FeederFilteredQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = MonthlyRevenueBilledSerializer

    def get_queryset(self):
        queryset = MonthlyRevenueBilled.objects.all()
        queryset = self.filter_by_location(queryset)
        month_from, month_to = get_date_range_from_request(self.request, 'month')

        if month_from and month_to:
            queryset = queryset.filter(month__range=(month_from, month_to))
        elif month_from:
            queryset = queryset.filter(month__gte=month_from)
        elif month_to:
            queryset = queryset.filter(month__lte=month_to)

        return queryset


class MonthlyEnergyBilledViewSet(FeederFilteredQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = MonthlyEnergyBilledSerializer

    def get_queryset(self):
        queryset = MonthlyEnergyBilled.objects.all()
        queryset = self.filter_by_location(queryset)
        month_from, month_to = get_date_range_from_request(self.request, 'month')

        if month_from and month_to:
            queryset = queryset.filter(month__range=(month_from, month_to))
        elif month_from:
            queryset = queryset.filter(month__gte=month_from)
        elif month_to:
            queryset = queryset.filter(month__lte=month_to)

        return queryset


class MonthlyCustomerStatsViewSet(FeederFilteredQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = MonthlyCustomerStatsSerializer

    def get_queryset(self):
        queryset = MonthlyCustomerStats.objects.all()
        queryset = self.filter_by_location(queryset)
        month_from, month_to = get_date_range_from_request(self.request, 'month')

        if month_from and month_to:
            queryset = queryset.filter(month__range=(month_from, month_to))
        elif month_from:
            queryset = queryset.filter(month__gte=month_from)
        elif month_to:
            queryset = queryset.filter(month__lte=month_to)

        return queryset


# Aggregated Metrics Endpoint
from rest_framework.views import APIView

class FeederMetricsView(APIView):
    def get(self, request):
        month_from = request.GET.get('month_from')
        month_to = request.GET.get('month_to')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        top_n = request.GET.get('top_n')
        bottom_n = request.GET.get('bottom_n')

        if month_from:
            month_from = datetime.strptime(month_from, "%Y-%m-%d").date()
        if month_to:
            month_to = datetime.strptime(month_to, "%Y-%m-%d").date()
        if date_from:
            date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        if date_to:
            date_to = datetime.strptime(date_to, "%Y-%m-%d").date()

        feeders = get_filtered_feeders(request)
        metrics = []

        for feeder in feeders:
            energy_billed = MonthlyEnergyBilled.objects.filter(
                feeder=feeder,
                month__range=(month_from, month_to)
            ).aggregate(total=Sum('energy_mwh'))['total'] or 0

            energy_delivered = DailyEnergyDelivered.objects.filter(
                feeder=feeder,
                date__range=(date_from, date_to)
            ).aggregate(total=Sum('energy_mwh'))['total'] or 0

            revenue_collected = DailyRevenueCollected.objects.filter(
                feeder=feeder,
                date__range=(date_from, date_to)
            ).aggregate(total=Sum('amount'))['total'] or 0

            revenue_billed = MonthlyRevenueBilled.objects.filter(
                feeder=feeder,
                month__range=(month_from, month_to)
            ).aggregate(total=Sum('amount'))['total'] or 0

            collection_eff = (revenue_collected / revenue_billed) * 100 if revenue_billed else 0
            billing_eff = (energy_billed / energy_delivered) * 100 if energy_delivered else 0
            atc_c = 100 - (billing_eff * collection_eff / 100)

            metrics.append({
                "feeder_id": feeder.id,
                "feeder": feeder.name,
                "energy_billed": energy_billed,
                "energy_delivered": energy_delivered,
                "revenue_collected": revenue_collected,
                "revenue_billed": revenue_billed,
                "collection_efficiency": round(collection_eff, 2),
                "billing_efficiency": round(billing_eff, 2),
                "atc_c": round(atc_c, 2),
            })

        # Sort and slice by ATC&C
        metrics.sort(key=lambda x: x['atc_c'])
        if top_n:
            metrics = metrics[:int(top_n)]
        elif bottom_n:
            metrics = metrics[-int(bottom_n):]

        return Response(metrics)


class CommercialMetricsSummaryView(APIView):
    def get(self, request):
        metrics = calculate_derived_metrics(request)
        return Response(metrics)
    


class SalesRepresentativeViewSet(viewsets.ModelViewSet):
    queryset = SalesRepresentative.objects.all()
    serializer_class = SalesRepresentativeSerializer


class SalesRepPerformanceViewSet(viewsets.ModelViewSet):
    serializer_class = SalesRepPerformanceSerializer

    def get_queryset(self):
        qs = SalesRepPerformance.objects.all()
        sales_rep_slug = self.request.GET.get('sales_rep')

        if sales_rep_slug:
            qs = qs.filter(sales_rep__slug=sales_rep_slug)

        month_from, month_to = get_date_range_from_request(self.request, 'month')
        if month_from and month_to:
            qs = qs.filter(month__range=(month_from, month_to))
        elif month_from:
            qs = qs.filter(month__gte=month_from)
        elif month_to:
            qs = qs.filter(month__lte=month_to)

        return qs

class SalesRepMetricsView(APIView):
    def get(self, request):
        data = get_sales_rep_performance_summary(request)
        return Response(data)


class DailyCollectionViewSet(viewsets.ModelViewSet):
    serializer_class = DailyCollectionSerializer

    def get_queryset(self):
        feeders = get_filtered_feeders(self.request)
        date_from, date_to = get_date_range_from_request(self.request, 'date')

        qs = DailyCollection.objects.filter(feeder__in=feeders)

        if date_from and date_to:
            qs = qs.filter(date__range=(date_from, date_to))
        elif date_from:
            qs = qs.filter(date__gte=date_from)
        elif date_to:
            qs = qs.filter(date__lte=date_to)

        collection_type = self.request.GET.get('collection_type')
        if collection_type:
            qs = qs.filter(collection_type=collection_type)

        return qs


from rest_framework.views import APIView
from rest_framework.response import Response
from commercial.analytics import get_commercial_overview_data

class CommercialOverviewAPIView(APIView):
    def get(self, request):
        # Parse optional date range filters (monthly or range)
        mode = request.query_params.get('mode', 'monthly')
        year = int(request.query_params.get('year', 2023))
        month = int(request.query_params.get('month', 1))
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')

        data = get_commercial_overview_data(mode, year, month, from_date, to_date)
        return Response(data)



@api_view(["GET"])
def commercial_all_states_view(request):
    mode = request.query_params.get("mode", "monthly")
    year = int(request.query_params.get("year", date.today().year))
    month = int(request.query_params.get("month", date.today().month))
    from_date = request.query_params.get("from_date")
    to_date = request.query_params.get("to_date")

    # Pick date logic
    if mode == "monthly":
        period_start = date(year, month, 1)
        period_end = period_start + relativedelta(months=1)
    else:
        period_start = parse_date(from_date) or date.today().replace(day=1)
        period_end = parse_date(to_date) or date.today()

    results = []

    for state in State.objects.all():
        filter_by_state_and_date = {
            "feeder__district__state": state,
            "date__gte": period_start,
            "date__lt": period_end,
        }

        delivered_sum = EnergyDelivered.objects.filter(
            feeder__district__state__name=state,
            date__gte=period_start,
            date__lt=period_end
        ).aggregate(total=Sum("energy_mwh"))

        delivered = Decimal(delivered_sum.get("total") or 0)


        billed = (
            MonthlyRevenueBilled.objects.filter(
                feeder__district__state=state,
                month__year=period_start.year,
                month__month=period_start.month,
            )
            .aggregate(Sum("amount"))["amount__sum"]
            or Decimal(0)
        )
        collected = (
            DailyCollection.objects.filter(**filter_by_state_and_date)
            .aggregate(Sum("amount"))["amount__sum"]
            or Decimal(0)
        )

        # customer_records = CustomerRecord.objects.filter(
        #     district__state=state
        # ).aggregate(Sum("revenue_billed"), Sum("collections"), Sum("total_customers"))

        try:
            billing_eff = (Decimal(billed) / Decimal(delivered)) if delivered else Decimal(0)
            collection_eff = (Decimal(collected) / Decimal(billed)) if billed else Decimal(0)
            atcc = (billing_eff * collection_eff) * Decimal("100")

            billing_eff *= Decimal("100")
            collection_eff *= Decimal("100")
        except (InvalidOperation, ZeroDivisionError):
            atcc = billing_eff = collection_eff = Decimal(0)

        # revenue_per_customer = (
        #     Decimal(customer_records["revenue_billed__sum"] or 0) /
        #     Decimal(customer_records["total_customers__sum"] or 1)
        # )
        # collection_per_customer = (
        #     Decimal(customer_records["collections__sum"] or 0) /
        #     Decimal(customer_records["total_customers__sum"] or 1)
        # )

        # response_record = CustomerResponse.objects.filter(state=state, date__gte=period_start, date__lt=period_end)
        # total = response_record.aggregate(Sum("total_requests"))["total_requests__sum"] or 0
        # resolved = response_record.aggregate(Sum("resolved"))["resolved__sum"] or 0
        # try:
        #     response_rate = Decimal(resolved) / Decimal(total) * Decimal(100) if total else Decimal(0)
        # except (InvalidOperation, ZeroDivisionError):
        #     response_rate = Decimal(0)

        results.append({
            "state": state.name,
            "energy_delivered": float(delivered),
            "energy_billed": float(billed),
            "energy_collected": float(collected),
            "atcc": {"actual": float(atcc), "target": 65},  # Target is placeholder
            "billing_efficiency": {"actual": float(billing_eff), "target": 75},
            "collection_efficiency": {"actual": float(collection_eff), "target": 70},
            # "customer_response_rate": {"actual": float(response_rate), "target": 67},
            # "revenue_billed_per_customer": float(revenue_per_customer),
            # "collections_per_customer": float(collection_per_customer),
        })

    return Response(results)
