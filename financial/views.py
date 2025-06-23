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

from django.db.models import Sum
from django.utils.timezone import now
from rest_framework.decorators import api_view
from rest_framework.response import Response
from datetime import date
from dateutil.relativedelta import relativedelta # type: ignore
from commercial.models import MonthlyCommercialSummary, DailyRevenueCollected, DailyEnergyDelivered
from django.db.models import Q
from .metrics import get_financial_feeder_data
from commercial.models import SalesRepresentative
from django.db.models import Count
from datetime import datetime, timedelta
from rest_framework import status
from commercial.serializers import SalesRepresentativeSerializer



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
    






@api_view(["GET"])
def financial_overview_view(request):
    year = int(request.query_params.get("year", date.today().year))
    month = request.query_params.get("month")
    state_name = request.query_params.get("state")
    district_name = request.query_params.get("business_district")

    # Filters
    commercial_filter = Q(month__year=year)
    expense_filter = Q(date__year=year)

    if district_name:
        commercial_filter &= Q(sales_rep__assigned_feeders__business_district__name__iexact=district_name)
        expense_filter &= Q(district__name__iexact=district_name)
    elif state_name:
        commercial_filter &= Q(sales_rep__assigned_feeders__business_district__state__name__iexact=state_name)
        expense_filter &= Q(district__state__name__iexact=state_name)

    # --- Monthly Commercial Collections (Always full year) ---
    monthly_collections = MonthlyCommercialSummary.objects.filter(commercial_filter).values_list("month__month").annotate(
        total_collections=Sum("revenue_collected"),
        total_billed=Sum("revenue_billed")
    )

    monthly_data = {m: {"collections": 0, "billed": 0} for m in range(1, 13)}
    for m, collected, billed in monthly_collections:
        monthly_data[m]["collections"] = float(collected or 0)
        monthly_data[m]["billed"] = float(billed or 0)

    monthly_summaries = [
        {
            "month": date(year, m, 1).strftime("%b"),
            "collections": monthly_data[m]["collections"],
            "billed": monthly_data[m]["billed"],
        }
        for m in range(1, 13)
    ]

    # --- Revenue/Collection and Expenses (Filtered by month if provided) ---
    if month:
        try:
            month = int(month)
            start_month = date(year, month, 1)
            end_month = start_month + relativedelta(months=1)

            monthly_filter = Q(month__gte=start_month, month__lt=end_month)
            expense_month_filter = Q(date__gte=start_month, date__lt=end_month)

            current_month_filter = commercial_filter & monthly_filter
            expense_filter &= expense_month_filter
        except ValueError:
            return Response({"error": "Invalid month format"}, status=400)
    else:
        current_month_filter = commercial_filter  # use whole year

    # Revenue/Collection for the month/year
    monthly_summary = MonthlyCommercialSummary.objects.filter(current_month_filter).aggregate(
        revenue_billed=Sum("revenue_billed"),
        revenue_collected=Sum("revenue_collected")
    )

    revenue_billed = float(monthly_summary["revenue_billed"] or 0)
    revenue_collected = float(monthly_summary["revenue_collected"] or 0)

    # Expenses for selected scope
    expenses = Expense.objects.filter(expense_filter)
    total_cost = float(expenses.aggregate(total=Sum("credit"))["total"] or 0)

    opex_breakdown = (
        expenses.values("opex_category__name")
        .annotate(total=Sum("credit"))
        .order_by("opex_category__name")
    )

    breakdown = [
        {
            "category": entry["opex_category__name"] or "Uncategorized",
            "amount": float(entry["total"] or 0)
        }
        for entry in opex_breakdown
    ]


    # --- Historical Financial Breakdown (last 5 months including selected) ---
    selected_month = int(request.query_params.get("month", date.today().month))
    selected_date = date(year, selected_month, 1)
    prev_months = [selected_date - relativedelta(months=i) for i in range(4, -1, -1)]

    historical_data = []

    for dt in prev_months:
        month_start = date(dt.year, dt.month, 1)
        month_end = month_start + relativedelta(months=1)

        # MonthlyCommercialSummary filters by month field
        summary_filter = commercial_filter & Q(month__gte=month_start, month__lt=month_end)

        # Expense filters by date field
        cost_filter = expense_filter & Q(date__gte=month_start, date__lt=month_end)

        summary = MonthlyCommercialSummary.objects.filter(summary_filter).aggregate(
            revenue_collected=Sum("revenue_collected"),
            revenue_billed=Sum("revenue_billed")
        )
        cost = Expense.objects.filter(cost_filter).aggregate(total=Sum("credit"))["total"] or 0

        historical_data.append({
            "month": dt.strftime("%b"),
            "total_cost": float(cost),
            "revenue_billed": float(summary["revenue_billed"] or 0),
            "revenue_collected": float(summary["revenue_collected"] or 0),
        })

    # Add deltas (percentage change from previous month)
    for i in range(1, len(historical_data)):
        for key in ["total_cost", "revenue_billed", "revenue_collected"]:
            prev = historical_data[i - 1][key]
            curr = historical_data[i][key]
            delta = ((curr - prev) / prev * 100) if prev else 0
            historical_data[i][f"{key}_delta"] = round(delta, 2)



    return Response({
        "monthly_summary": monthly_summaries,
        "revenue_billed": revenue_billed,
        "revenue_collected": revenue_collected,
        "total_cost": total_cost,
        "opex_breakdown": breakdown,
        "historical_summary": historical_data,
    })

@api_view(['GET'])
def financial_feeder_view(request):
    """
    Returns feeder-level financial metrics filtered by state or business district and date.
    Business district filter takes precedence.
    """
    data = get_financial_feeder_data(request)
    return Response(data)


@api_view(["GET"])
def sales_rep_performance_view(request, rep_id):
    try:
        rep = SalesRepresentative.objects.get(id=rep_id)
    except SalesRepresentative.DoesNotExist:
        return Response({"error": "Sales rep not found."}, status=status.HTTP_404_NOT_FOUND)

    mode = request.GET.get("mode", "monthly")
    year = int(request.GET.get("year", datetime.now().year))
    month = int(request.GET.get("month", datetime.now().month))

    start_date = datetime(year, month, 1)
    end_date = (start_date + relativedelta(months=1)) - timedelta(days=1)

    # Current month summary
    current_summary = MonthlyCommercialSummary.objects.filter(
        sales_rep=rep,
        month__range=(start_date, end_date)
    ).aggregate(
        revenue_billed=Sum("revenue_billed"),
        revenue_collected=Sum("revenue_collected"),
    )

    revenue_billed = current_summary["revenue_billed"] or 0
    revenue_collected = current_summary["revenue_collected"] or 0
    outstanding_billed = revenue_billed - revenue_collected

    # All-time
    all_time_summary = MonthlyCommercialSummary.objects.filter(sales_rep=rep).aggregate(
        all_time_billed=Sum("revenue_billed"),
        all_time_collected=Sum("revenue_collected")
    )
    outstanding_all_time = (all_time_summary["all_time_billed"] or 0) - (all_time_summary["all_time_collected"] or 0)

    # ---- Previous 4 Months ---- #
    monthly_summaries = []
    for i in range(4):
        ref_date = start_date - relativedelta(months=i)
        month_start = ref_date.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - timedelta(days=1)

        summary = MonthlyCommercialSummary.objects.filter(
            sales_rep=rep,
            month__range=(month_start, month_end)
        ).aggregate(
            revenue_billed=Sum("revenue_billed") or 0,
            revenue_collected=Sum("revenue_collected") or 0,
        )

        billed = summary["revenue_billed"] or 0
        collected = summary["revenue_collected"] or 0
        outstanding = billed - collected

        monthly_summaries.append({
            "month": month_start.strftime("%b"),
            "revenue_billed": billed,
            "revenue_collected": collected,
            "outstanding_billed": outstanding
        })

    monthly_summaries.reverse()

    return Response({
        "sales_rep": {
            "id": str(rep.id),
            "name": rep.name
        },
        "current": {
            "revenue_billed": revenue_billed,
            "revenue_collected": revenue_collected,
            "outstanding_billed": outstanding_billed
        },
        "outstanding_all_time": outstanding_all_time,
        "previous_months": monthly_summaries
    })

@api_view(["GET"])
def list_sales_reps(request):
    reps = SalesRepresentative.objects.all()[:10]
    data = SalesRepresentativeSerializer(reps, many=True).data
    return Response(data)


@api_view(["GET"])
def sales_rep_global_summary_view(request):
    mode = request.GET.get("mode", "monthly")

    if mode == "monthly":
        try:
            year = int(request.GET.get("year", datetime.now().year))
            month = int(request.GET.get("month", datetime.now().month))
            start_date = datetime(year, month, 1)
            end_date = (start_date + relativedelta(months=1)) - relativedelta(days=1)
        except (TypeError, ValueError):
            return Response({"error": "Invalid year or month for monthly mode"}, status=400)
    else:
        from common.filters import get_date_range_from_request
        start_date, end_date = get_date_range_from_request(request, "month")

    summary = MonthlyCommercialSummary.objects.filter(
        month__range=(start_date, end_date)
    ).aggregate(
        total_billed=Sum("revenue_billed"),
        total_collected=Sum("revenue_collected"),
        active_accounts=Count("id")
    )

    total_billed = summary["total_billed"] or 0
    total_collected = summary["total_collected"] or 0
    active_accounts = summary["active_accounts"] or 0

    return Response({
        "daily_run_rate": total_billed / 30,
        "collections_on_outstanding": total_collected,
        "active_accounts": active_accounts,
        "suspended_accounts": 0
    })


import random
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import date
from django.db.models import Sum
from decimal import Decimal

from financial.models import Expense
from commercial.models import MonthlyCommercialSummary
from common.models import State


class FinancialAllStatesView(APIView):
    def get(self, request):
        year = int(request.GET.get("year"))
        month = int(request.GET.get("month"))
        target_month = date(year, month, 1)

        results = []

        for state in State.objects.all():
            # --- Total Cost (from Expenses) ---
            expense_total = Expense.objects.filter(
                date__year=year,
                date__month=month,
                district__state=state
            ).aggregate(total_cost=Sum("credit"))["total_cost"] or Decimal("0")

            # --- Revenue Billed and Collections (from MonthlyCommercialSummary) ---
            sales_reps = SalesRepresentative.objects.filter(
                assigned_transformers__feeder__business_district__state=state
            ).distinct()

            commercial_data = MonthlyCommercialSummary.objects.filter(
                month=target_month,
                sales_rep__in=sales_reps
            ).aggregate(
                revenue_billed=Sum("revenue_billed"),
                collections=Sum("revenue_collected")
            )

            revenue_billed = commercial_data["revenue_billed"] or Decimal("0")
            collections = commercial_data["collections"] or Decimal("0")

            # --- Random Tariff Data ---
            myto_tariff = Decimal(random.choice([59, 60, 61]))
            actual_tariff = Decimal(random.choice([70, 72, 68]))
            tariff_loss = myto_tariff - actual_tariff

            # --- Compile State Metrics ---
            results.append({
                "state": state.name,
                "total_cost": round(expense_total, 2),
                "revenue_billed": round(revenue_billed, 2),
                "collections": round(collections, 2),
                "myto_allowed_tariff": f"{myto_tariff}",
                "actual_tariff_collected": f"{actual_tariff}",
                "tariff_loss": f"{tariff_loss}"
            })

        return Response(results, status=status.HTTP_200_OK)



import random
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import date
from django.db.models import Sum
from decimal import Decimal

from financial.models import Expense
from commercial.models import MonthlyCommercialSummary
from common.models import BusinessDistrict

class FinancialAllBusinessDistrictsView(APIView):
    def get(self, request):
        year = int(request.GET.get("year"))
        month = int(request.GET.get("month"))
        state_name = request.GET.get("state")

        if not state_name:
            return Response({"error": "state is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            state = State.objects.get(name__iexact=state_name)
        except State.DoesNotExist:
            return Response({"error": "State not found"}, status=status.HTTP_404_NOT_FOUND)

        target_month = date(year, month, 1)
        results = []

        districts = BusinessDistrict.objects.filter(state=state)

        for district in districts:
            # Total Cost (Expense model)
            cost = Expense.objects.filter(
                district=district,
                date__year=year,
                date__month=month
            ).aggregate(total_cost=Sum("credit"))["total_cost"] or Decimal("0")

            # Get all sales reps mapped to district via feeder
            sales_reps = SalesRepresentative.objects.filter(
                assigned_transformers__feeder__business_district=district
            ).distinct()

            commercial_data = MonthlyCommercialSummary.objects.filter(
                month=target_month,
                sales_rep__in=sales_reps
            ).aggregate(
                revenue_billed=Sum("revenue_billed"),
                collections=Sum("revenue_collected")
            )

            billed = commercial_data["revenue_billed"] or Decimal("0")
            collected = commercial_data["collections"] or Decimal("0")

            # Random Tariff Loss (simulate)
            tariff_loss = Decimal(random.randint(10, 50))

            results.append({
                "district": district.name,
                "total_cost": round(cost, 2),
                "revenue_billed": round(billed, 2),
                "collections": round(collected, 2),
                "tariff_loss": f"{tariff_loss}"
            })

        return Response(results, status=status.HTTP_200_OK)



from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import date
from django.db.models import Sum
from decimal import Decimal
from random import randint

from common.models import Band, Feeder
from commercial.models import MonthlyCommercialSummary, SalesRepresentative
from financial.models import Expense
from technical.models import EnergyDelivered


class FinancialServiceBandMetricsView(APIView):
    def get(self, request):
        try:
            year = int(request.GET.get("year"))
            month = int(request.GET.get("month"))
        except (TypeError, ValueError):
            return Response({"error": "Invalid or missing 'year' or 'month' parameters."},
                            status=status.HTTP_400_BAD_REQUEST)

        state_name = request.GET.get("state")
        selected_date = date(year, month, 1)

        bands = Band.objects.all()
        results = []

        for band in bands:
            # Get feeders for the band (filtered by state if provided)
            feeders = Feeder.objects.filter(band=band)
            if state_name:
                feeders = feeders.filter(business_district__state__name__iexact=state_name)

            if not feeders.exists():
                continue

            # Get distinct business districts tied to the feeders
            district_ids = feeders.values_list("business_district_id", flat=True).distinct()

            # Get all sales reps tied to feeders via transformers
            sales_reps = SalesRepresentative.objects.filter(
                assigned_transformers__feeder__in=feeders
            ).distinct()

            # Aggregate commercial revenue & collections
            commercial = MonthlyCommercialSummary.objects.filter(
                sales_rep__in=sales_reps,
                month=selected_date
            ).aggregate(
                revenue_billed=Sum("revenue_billed"),
                revenue_collected=Sum("revenue_collected")
            )

            revenue_billed = commercial["revenue_billed"] or Decimal("0")
            revenue_collected = commercial["revenue_collected"] or Decimal("0")

            # Aggregate total cost from expenses (filter by business districts)
            total_cost = Expense.objects.filter(
                district__in=district_ids,
                date__year=year,
                date__month=month
            ).aggregate(total=Sum("credit"))["total"] or Decimal("0")

            # Aggregate energy delivered
            energy_delivered = EnergyDelivered.objects.filter(
                feeder__in=feeders,
                date__year=year,
                date__month=month
            ).aggregate(total_energy=Sum("energy_mwh"))["total_energy"] or Decimal("0")

            # Tariff Calculations
            myto_tariff = Decimal(randint(55, 65))  # Static/random per band
            actual_tariff = (
                round(revenue_collected / energy_delivered, 2)
                if energy_delivered else Decimal("0")
            )
            tariff_loss = round(myto_tariff - actual_tariff, 2)

            results.append({
                "band": band.name,
                "total_cost": round(total_cost, 2),
                "revenue_billed": round(revenue_billed, 2),
                "collections": round(revenue_collected, 2),
                "myto_allowed_tariff": f"{myto_tariff}",
                "actual_tariff_collected": f"{actual_tariff}",
                "tariff_loss": f"{tariff_loss}"
            })

        return Response(results, status=status.HTTP_200_OK)



from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum
from datetime import date, timedelta
from commercial.models import MonthlyCommercialSummary


class DailyCollectionsByMonthView(APIView):
    def get(self, request):
        try:
            year = int(request.GET.get("year"))
            month = int(request.GET.get("month"))
            start_date = date(year, month, 1)
        except (TypeError, ValueError):
            return Response({"error": "Valid 'year' and 'month' query parameters are required."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Get last day of the month
        next_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = next_month - timedelta(days=1)

        results = []

        current_day = start_date
        while current_day <= end_date:
            total_collections = MonthlyCommercialSummary.objects.filter(
                month=current_day
            ).aggregate(
                total=Sum("revenue_collected")
            )["total"] or 0

            results.append({
                "day": current_day.day,
                "value": round(total_collections, 2)
            })

            current_day += timedelta(days=1)

        return Response(results, status=status.HTTP_200_OK)
