from rest_framework import viewsets
from .models import *
from .serializers import *
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, F, FloatField, ExpressionWrapper, Q
from common.models import Feeder, State, BusinessDistrict
from datetime import datetime
from .utils import get_filtered_feeders
from commercial.date_filters import get_date_range_from_request
from commercial.mixins import FeederFilteredQuerySetMixin
from commercial.utils import get_filtered_customers
from commercial.metrics import calculate_derived_metrics, get_sales_rep_performance_summary
from rest_framework.decorators import api_view
from decimal import Decimal, InvalidOperation
from technical.models import EnergyDelivered, HourlyLoad, FeederInterruption
from financial.models import MonthlyRevenueBilled, Expense
from commercial.models import DailyCollection
from django.utils.dateparse import parse_date
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db.models import Sum, FloatField, F, ExpressionWrapper, Case, When, Value, Count, Avg
from django.db.models import DurationField
import random


from decimal import Decimal, ROUND_HALF_UP

def round_two_places(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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
        # Parse query parameters
        mode = request.query_params.get('mode', 'monthly')
        year = int(request.query_params.get('year', datetime.today().year))
        month = int(request.query_params.get('month', datetime.today().month))
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')

        # Delegate to analytics logic
        data = get_commercial_overview_data(
            mode=mode,
            year=year,
            month=month,
            from_date=from_date,
            to_date=to_date
        )

        return Response(data)



def round_two_places(val):
    return Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def smart_target(value, variation=0.1):
    try:
        value = Decimal(str(value))  # ensure input is Decimal
        percent_shift = Decimal(str(random.uniform(-variation, variation)))
        return float(round_two_places(value * (Decimal("1") + percent_shift)))
    except:
        return 0  


@api_view(["GET"])
def commercial_all_states_view(request):
    mode = request.query_params.get("mode", "monthly")
    year = int(request.query_params.get("year", date.today().year))
    month = int(request.query_params.get("month", date.today().month))
    from_date = request.query_params.get("from_date")
    to_date = request.query_params.get("to_date")

    if mode == "monthly":
        current_start = date(year, month, 1)
        current_end = current_start + relativedelta(months=1)
        previous_start = current_start - relativedelta(months=1)
        previous_end = current_start
    else:
        current_start = parse_date(from_date) or date.today().replace(day=1)
        current_end = parse_date(to_date) or date.today()
        previous_start = current_start - (current_end - current_start)
        previous_end = current_start

    results = []

    for state in State.objects.all():
        def summary_agg(start, end):
            summaries = MonthlyCommercialSummary.objects.filter(
                sales_rep__assigned_feeders__business_district__state=state,
                month__gte=start,
                month__lt=end,
            ).distinct()

            billed = summaries.aggregate(Sum("revenue_billed"))["revenue_billed__sum"] or Decimal(0)
            collected = summaries.aggregate(Sum("revenue_collected"))["revenue_collected__sum"] or Decimal(0)
            cust_billed = summaries.aggregate(Sum("customers_billed"))["customers_billed__sum"] or 0
            cust_resp = summaries.aggregate(Sum("customers_responded"))["customers_responded__sum"] or 0

            return billed, collected, cust_billed, cust_resp

        def delivered_agg(start, end):
            return EnergyDelivered.objects.filter(
                feeder__business_district__state=state,
                date__gte=start,
                date__lt=end
            ).aggregate(Sum("energy_mwh"))["energy_mwh__sum"] or Decimal(0)

        # Current
        revenue_billed, revenue_collected, cust_billed, cust_resp = summary_agg(current_start, current_end)
        energy_delivered = delivered_agg(current_start, current_end)
        energy_billed = MonthlyEnergyBilled.objects.filter(
            feeder__business_district__state=state,
            month__gte=current_start,
            month__lt=current_end
        ).aggregate(Sum("energy_mwh"))["energy_mwh__sum"] or Decimal(0)

        # Previous
        prev_billed, prev_collected, prev_cust_billed, prev_cust_resp = summary_agg(previous_start, previous_end)
        prev_delivered = delivered_agg(previous_start, previous_end)
        prev_energy_billed = MonthlyEnergyBilled.objects.filter(
            feeder__business_district__state=state,
            month__gte=previous_start,
            month__lt=previous_end
        ).aggregate(Sum("energy_mwh"))["energy_mwh__sum"] or Decimal(0)

        def calc_efficiencies(billed, collected, delivered, energy_billed):
            try:
                billing_eff = (Decimal(energy_billed) / Decimal(delivered)) * 100 if delivered else Decimal(0)
                collection_eff = (Decimal(collected) / Decimal(billed)) * 100 if billed else Decimal(0)
                atcc = (Decimal(1) - ((billing_eff / 100) * (collection_eff / 100))) * 100
            except (InvalidOperation, ZeroDivisionError):
                billing_eff = collection_eff = atcc = Decimal(0)
            return billing_eff, collection_eff, atcc

        billing_eff, collection_eff, atcc = calc_efficiencies(
            revenue_billed, revenue_collected, energy_delivered, energy_billed
        )
        prev_billing_eff, prev_collection_eff, prev_atcc = calc_efficiencies(
            prev_billed, prev_collected, prev_delivered, prev_energy_billed
        )

        def percentage_delta(current, previous):
            if previous and previous != 0:
                return round(float(((Decimal(current) - Decimal(previous)) / Decimal(previous)) * 100), 2)
            return None

        results.append({
            "state": state.name,
            "energy_delivered": {
                "actual": float(round_two_places(energy_delivered)),
                "delta": percentage_delta(energy_delivered, prev_delivered)
            },
            "energy_billed": {
                "actual": float(round_two_places(energy_billed)),
                "delta": percentage_delta(energy_billed, prev_energy_billed)
            },
            "energy_collected": {
                "actual": float(round_two_places(revenue_collected)),
                "delta": percentage_delta(revenue_collected, prev_collected)
            },
            "atcc": {
                "actual": float(round_two_places(atcc)),
                "delta": percentage_delta(atcc, prev_atcc),
                "target": smart_target(atcc)
            },
            "billing_efficiency": {
                "actual": float(round_two_places(billing_eff)),
                "delta": percentage_delta(billing_eff, prev_billing_eff),
                "target": smart_target(billing_eff)
            },
            "collection_efficiency": {
                "actual": float(round_two_places(collection_eff)),
                "delta": percentage_delta(collection_eff, prev_collection_eff),
                "target": smart_target(collection_eff)
            },
            "customer_response_rate": {
                "actual": float(round_two_places((cust_resp / cust_billed) * 100 if cust_billed else 0)),
                "delta": percentage_delta(
                    (cust_resp / cust_billed * 100 if cust_billed else 0),
                    (prev_cust_resp / prev_cust_billed * 100 if prev_cust_billed else 0)
                ),
                "target": smart_target((cust_resp / cust_billed * 100 if cust_billed else 0))
            },
            "revenue_billed_per_customer": {
                "actual": float(round_two_places(revenue_billed / cust_billed)) if cust_billed else 0,
                "delta": percentage_delta(
                    (revenue_billed / cust_billed) if cust_billed else 0,
                    (prev_billed / prev_cust_billed) if prev_cust_billed else 0
                )
            },
            "collections_per_customer": {
                "actual": float(round_two_places(revenue_collected / cust_billed)) if cust_billed else 0,
                "delta": percentage_delta(
                    (revenue_collected / cust_billed) if cust_billed else 0,
                    (prev_collected / prev_cust_billed) if prev_cust_billed else 0
                )
            },
        })

    return Response(results)



@api_view(["GET"])
def commercial_state_metrics_view(request):
    state_name = request.query_params.get("state")
    mode = request.query_params.get("mode", "monthly")
    year = int(request.query_params.get("year", date.today().year))
    month = int(request.query_params.get("month", date.today().month))
    from_date = request.query_params.get("from_date")
    to_date = request.query_params.get("to_date")

    state = State.objects.filter(name__iexact=state_name).first()
    if not state:
        return Response({"error": "Invalid state"}, status=400)

    def generate_month_list(reference_date):
        return [reference_date - relativedelta(months=i) for i in range(4, -1, -1)]

    selected_date = (
        date(year, month, 1) if mode == "monthly" else parse_date(to_date) or date.today()
    )
    months = generate_month_list(selected_date)

    data = []

    for m in months:
        reps = SalesRepresentative.objects.filter(
            assigned_feeders__business_district__state=state
        ).distinct()

        summaries = MonthlyCommercialSummary.objects.filter(
            sales_rep__in=reps,
            month__year=m.year,
            month__month=m.month,
        )

        delivered = EnergyDelivered.objects.filter(
            feeder__business_district__state=state,
            date__year=m.year,
            date__month=m.month,
        ).aggregate(Sum("energy_mwh"))["energy_mwh__sum"] or Decimal(0)

        summary_totals = summaries.aggregate(
            revenue_collected=Sum("revenue_collected"),
            revenue_billed=Sum("revenue_billed"),
            customers_billed=Sum("customers_billed"),
            customers_responded=Sum("customers_responded"),
        )

        revenue_collected = summary_totals["revenue_collected"] or Decimal(0)
        revenue_billed = summary_totals["revenue_billed"] or Decimal(0)
        customers_billed = summary_totals["customers_billed"] or 1  # Avoid divide by zero
        customers_responded = summary_totals["customers_responded"] or 0

        # Metrics
        collection_eff = (
            (revenue_collected / revenue_billed) * 100
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if revenue_billed else Decimal(0)

        billing_eff = (
            ((revenue_billed/50) / delivered) * 100
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if delivered else Decimal(0)

        atcc = (
            (billing_eff * collection_eff / 100)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        energy_collected = (
            (delivered * collection_eff / 100)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        response_rate = (
            (Decimal(customers_responded) / Decimal(customers_billed)) * 100
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if customers_billed else Decimal(0)

        revenue_per_customer = (
            revenue_billed / Decimal(customers_billed)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        collection_per_customer = (
            revenue_collected / Decimal(customers_billed)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        data.append({
            "month": m.strftime("%b"),
            "energy_delivered": float(delivered),
            "revenue_billed": float(revenue_billed),  # Still money
            "energy_collected": float(energy_collected),  # Energy estimated from delivery × CE
            "billing_efficiency": float(billing_eff),
            "collection_efficiency": float(collection_eff),
            "atcc": float(atcc),
            "customer_response_rate": float(response_rate),
            "revenue_billed_per_customer": float(revenue_per_customer),
            "collections_per_customer": float(collection_per_customer),
        })

    return Response(data)



@api_view(["GET"])
def commercial_all_business_districts_view(request):
    state_name = request.query_params.get("state")
    year = int(request.query_params.get("year", date.today().year))
    month = int(request.query_params.get("month", date.today().month))

    # Determine the selected month range
    period_start = date(year, month, 1)
    period_end = period_start + relativedelta(months=1)

    districts = BusinessDistrict.objects.filter(state__name__iexact=state_name)
    result = []

    for district in districts:
        # Energy Delivered (MWh to GWh)
        energy_delivered = EnergyDelivered.objects.filter(
            feeder__business_district=district,
            date__gte=period_start,
            date__lt=period_end,
        ).aggregate(Sum("energy_mwh"))['energy_mwh__sum'] or 0

        energy_delivered /= 1000

        # Commercial Summary
        feeders = district.feeders.all()
        reps = SalesRepresentative.objects.filter(assigned_feeders__in=feeders).distinct()
        summaries = MonthlyCommercialSummary.objects.filter(
            sales_rep__in=reps,
            month__year=period_start.year,
            month__month=period_start.month,
        )

        revenue_billed = summaries.aggregate(Sum("revenue_billed"))['revenue_billed__sum'] or 0
        revenue_collected = summaries.aggregate(Sum("revenue_collected"))['revenue_collected__sum'] or 0

        billing_efficiency = ((revenue_billed/1000) / energy_delivered) if energy_delivered else 0
        collection_efficiency = (revenue_collected / revenue_billed * 100) if revenue_billed else 0
        atcc = billing_efficiency * collection_efficiency / 100 if energy_delivered and revenue_billed else 0

        result.append({
            "name": district.name,
            "energy_delivered": round(energy_delivered, 2),
            "revenue_billed": round(revenue_billed , 2),   
            
            "revenue_collected": round(revenue_collected , 2),
            "billing_efficiency": round(billing_efficiency, 2),
            "collection_efficiency": round(collection_efficiency, 2),
            "atcc": round(atcc, 2),
        })

    return Response(result)


# Helper
def NullIfZero(field):
    return Case(
        When(**{f'{field.name}': 0}, then=Value(None)),
        default=field,
        output_field=FloatField(),
    )

@api_view(['GET'])
def top_least_feeders_atcc(request):
    feeders = get_filtered_feeders(request)
    if feeders is None:
        return Response([], status=200)

    annotated = feeders.annotate(
        energy_delivered=Sum('dailyenergydelivered__energy_mwh'),
        energy_billed=Sum('monthlyenergybilled__energy_mwh'),
        revenue_collected=Sum('dailyrevenuecollected__amount'),
        revenue_billed=Sum('commercial_monthly_revenue_billed__amount'),
    ).annotate(
        billing_efficiency=ExpressionWrapper(
            100 * F('energy_billed') / NullIfZero(F('energy_delivered')),
            output_field=FloatField()
        ),
        collection_efficiency=ExpressionWrapper(
            100 * F('revenue_collected') / NullIfZero(F('revenue_billed')),
            output_field=FloatField()
        ),
    ).annotate(
        atcc=ExpressionWrapper(
            100 - ((F('billing_efficiency') * F('collection_efficiency')) / 100),
            output_field=FloatField()
        )
    )

    # Example response structure (adjust as needed)
    result = [
        {
            "name": f.name,
            "atcc": f.atcc,
            "billing_efficiency": f.billing_efficiency,
            "collection_efficiency": f.collection_efficiency,
        }
        for f in annotated
    ]
    return Response(result, status=200)


@api_view(['GET'])
def feeder_metrics(request):
    feeders = get_filtered_feeders(request)
    date_filter = get_date_range_from_request(request)

    queryset = feeders.filter(**date_filter).annotate(
        energy_delivered=Sum('dailyenergydelivered__energy_mwh'),
        energy_billed=Sum('monthlyenergybilled__energy_mwh'),
        energy_collected=Sum('dailyrevenuecollected__amount'),
        atcc=ExpressionWrapper(
            100 - (
                (100 - F('billing_efficiency')) *
                (100 - F('collection_efficiency')) / 100
            ),
            output_field=FloatField()
        )
    ).values('name', 'energy_delivered', 'energy_billed', 'energy_collected', 'atcc')

    return Response(queryset)



from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator

DEFAULT_TARIFF_PER_MWH = Decimal("50000")

@method_decorator(cache_page(60 * 5), name='dispatch')
class OverviewAPIView(APIView):
    def get(self, request):
        try:
            month = int(request.GET.get("month"))
            year = int(request.GET.get("year"))
            target = datetime(year, month, 1)
        except (TypeError, ValueError):
            target = None

        from_date_str = request.GET.get("from")
        to_date_str = request.GET.get("to")
        from_date = datetime.strptime(from_date_str, "%Y-%m-%d") if from_date_str else None
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d") if to_date_str else None

        if from_date and to_date:
            current = from_date.replace(day=1)
            months = []
            while current <= to_date:
                months.append(current)
                current += relativedelta(months=1)
        else:
            target = target or datetime.today().replace(day=1)
            months = [(target - relativedelta(months=i)).replace(day=1) for i in range(5)][::-1]

        overview_data = []

        for m in months:
            comm = MonthlyCommercialSummary.objects.filter(month=m).aggregate(
                revenue_billed=Sum("revenue_billed"),
                revenue_collected=Sum("revenue_collected"),
                customers_billed=Sum("customers_billed"),
                customers_responded=Sum("customers_responded"),
            )
            tech = EnergyDelivered.objects.filter(date__year=m.year, date__month=m.month).aggregate(
                energy=Sum("energy_mwh")
            )
            billed_energy = MonthlyEnergyBilled.objects.filter(month=m).aggregate(
                energy=Sum("energy_mwh")
            )
            cost = Expense.objects.filter(date__year=m.year, date__month=m.month).aggregate(
                credit=Sum("credit")
            )

            loads = HourlyLoad.objects.filter(date__year=m.year, date__month=m.month).values('date').annotate(
                count=Count('id')
            )
            # hours_supplied = sum([entry['count'] for entry in loads]) / len(loads) if loads else 0

            hours_supplied = (
                loads.filter(load_mw__gt=0)
                .values('feeder', 'date')
                .annotate(hours=Count('hour', distinct=True))
            )

            if hours_supplied:
                avg_hours_supply = sum(entry['hours'] for entry in hours_supplied) / len(hours_supplied)
            else:
                avg_hours_supply = 0 

            # interruptions = FeederInterruption.objects.filter(
            #     occurred_at__year=m.year, occurred_at__month=m.month,
            #     restored_at__isnull=False
            # ).annotate(
            #     duration=ExpressionWrapper(F('restored_at') - F('occurred_at'), output_field=DurationField())
            # )

            # avg_duration = interruptions.aggregate(avg=Avg('duration'))['avg']
            # avg_duration_hours = avg_duration.total_seconds() / 3600 if avg_duration else 0

            # avg_turnaround = interruptions.aggregate(avg=Avg('duration'))['avg']
            # avg_turnaround_hours = avg_turnaround.total_seconds() / 3600 if avg_turnaround else 0

            billing_eff = (billed_energy['energy'] / tech['energy']) if tech['energy'] else 0
            collection_eff = (comm['revenue_collected'] / comm['revenue_billed']) if comm['revenue_billed'] else 0
            atcc = 1 - (billing_eff * collection_eff)
            energy_collected = comm['revenue_collected'] / DEFAULT_TARIFF_PER_MWH if comm['revenue_collected'] else 0

            overview_data.append({
                "month": m.strftime("%b"),
                "billing_efficiency": round(billing_eff * 100, 2),
                "collection_efficiency": round(collection_eff * 100, 2),
                "atcc": round(atcc * 100, 2),
                "revenue_billed": comm['revenue_billed'] or 0,
                "revenue_collected": comm['revenue_collected'] or 0,
                "energy_billed": billed_energy['energy'] or 0,
                "energy_delivered": tech['energy'] or 0,
                "energy_collected": round(energy_collected, 2),
                "customer_response_rate": round((comm['customers_responded'] / comm['customers_billed']) * 100, 2) if comm['customers_billed'] else 0,
                "total_cost": cost['credit'] or 0,
                "avg_hours_supply": round(avg_hours_supply, 2),
                # "avg_interruption_duration": round(avg_duration_hours, 2),
                # "avg_turnaround_time": round(avg_turnaround_hours, 2),
                "avg_interruption_duration": round(24 - avg_hours_supply, 2),
                "avg_turnaround_time": round(24 - avg_hours_supply, 2),
            })

        current = overview_data[-1]
        previous = overview_data[-2] if len(overview_data) > 1 else {}

        def delta(metric):
            if metric in current and metric in previous and previous[metric]:
                return round(((current[metric] - previous[metric]) / previous[metric]) * 100, 2)
            return None

        for metric in [
            "atcc",
            "billing_efficiency",
            "collection_efficiency",
            "revenue_billed",
            "revenue_collected",
            "energy_billed",
            "energy_delivered",
            "total_cost",
            "energy_collected",
            "customer_response_rate",
            "avg_hours_supply",
            "avg_interruption_duration",
            "avg_turnaround_time"
        ]:
            current[f"delta_{metric}"] = delta(metric)

        return Response({
            "current": current,
            "history": overview_data[:-1]
        })