# financial/views.py
import random
from random import randint
from datetime import date, datetime, timedelta
from calendar import monthrange
from decimal import Decimal
from dateutil.relativedelta import relativedelta  # type: ignore

from django.db.models import (
    Sum, Q, Count
)
from django.utils.timezone import now

from django_filters.rest_framework import DjangoFilterBackend

from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view

from .models import *
from .serializers import *
from .metrics import get_financial_feeder_data

from common.mixins import DistrictLocationFilterMixin
from common.models import (
    Feeder, State, BusinessDistrict, Band, DistributionTransformer
)

from commercial.models import (
    MonthlyCommercialSummary,
    DailyRevenueCollected,
    DailyEnergyDelivered,
    SalesRepresentative,
    DailyCollection
)
from commercial.serializers import SalesRepresentativeSerializer
from commercial.utils import get_filtered_feeders
from commercial.date_filters import get_date_range_from_request
from commercial.metrics import get_total_collections

from financial.models import Opex
from financial.metrics import (
    get_total_cost,
    get_total_revenue_billed,
    get_opex_breakdown,
    get_tariff_loss
)

from technical.models import (
    FeederEnergyMonthly,
    FeederEnergyDaily,
    EnergyDelivered
)



class OpexCategoryViewSet(viewsets.ModelViewSet):
    queryset = OpexCategory.objects.all()
    serializer_class = OpexCategorySerializer


class OpexViewSet(DistrictLocationFilterMixin, viewsets.ModelViewSet):
    # queryset = Expense.objects.all()
    serializer_class = OpexSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {'district', 'gl_breakdown', 'opex_category', 'date'}

    def get_queryset(self):
        qs = Opex.objects.all()
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
    
class SalaryPaymentViewSet(viewsets.ModelViewSet):
    queryset = SalaryPayment.objects.all()
    serializer_class = SalaryPaymentSerializer
    filterset_fields = ["district", "month", "staff"]


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
    # ─── 1) PARAMS & BASE FILTERS ──────────────────────────────────────────────
    year = int(request.query_params.get("year", date.today().year))
    month = request.query_params.get("month")
    state_name = request.query_params.get("state")
    district_name = request.query_params.get("business_district")

    # Commercial summaries (MonthlyCommercialSummary.month)
    commercial_base = Q(month__year=year)
    # Opex (Opex.date), NBET/MO/Salaries (month), SalaryPayment(month)
    opex_base = Q(date__year=year)

    if district_name:
        commercial_base &= Q(sales_rep__assigned_feeders__business_district__name__iexact=district_name)
        opex_base &= Q(district__name__iexact=district_name)
        salary_loc   = Q(district__name__iexact=district_name)
    elif state_name:
        commercial_base &= Q(sales_rep__assigned_feeders__business_district__state__name__iexact=state_name)
        opex_base &= Q(district__state__name__iexact=state_name)
        salary_loc   = Q(district__state__name__iexact=state_name)
    else:
        salary_loc = Q()  # no location filter on SalaryPayment

    # ─── 2) MONTHLY ROLLOUP (FULL YEAR) ────────────────────────────────────────
    # Always show all 12 months of that year
    mon_qs = (
        MonthlyCommercialSummary.objects.filter(commercial_base)
        .values_list("month__month")
        .annotate(
            collections=Sum("revenue_collected"),
            billed=Sum("revenue_billed")
        )
    )
    tmp = {m: {"collections": 0, "billed": 0} for m in range(1, 13)}
    for m, col, bill in mon_qs:
        tmp[m]["collections"] = float(col or 0)
        tmp[m]["billed"]     = float(bill or 0)

    monthly_summary = [
        {
            "month": date(year, m, 1).strftime("%b"),
            **tmp[m]
        }
        for m in range(1, 13)
    ]

    # ─── 3) SELECTED–MONTH vs FULL–YEAR ──────────────────────────────────────
    if month:
        try:
            m = int(month)
            start = date(year, m, 1)
            end   = start + relativedelta(months=1)
        except ValueError:
            return Response({"error": "Invalid month"}, status=400)

        # refine filters to just that window
        commercial_filter = commercial_base & Q(month__gte=start, month__lt=end)
        opex_filter       = opex_base       & Q(date__gte=start,   date__lt=end)
        salary_filter     = salary_loc      & Q(month__gte=start,   month__lt=end)

        # NBET/MO invoices are per-month on .month
        invoice_window = Q(month__gte=start, month__lt=end)
    else:
        # whole year
        commercial_filter = commercial_base
        opex_filter       = opex_base
        salary_filter     = salary_loc
        invoice_window    = Q(month__year=year)

    # Revenue & collections for the selected window
    rev_aggr = MonthlyCommercialSummary.objects.filter(commercial_filter).aggregate(
        revenue_billed=Sum("revenue_billed"),
        revenue_collected=Sum("revenue_collected"),
    )
    revenue_billed   = float(rev_aggr["revenue_billed"]   or 0)
    revenue_collected= float(rev_aggr["revenue_collected"] or 0)

    # ─── 4) TOTAL COSTS ────────────────────────────────────────────────────────
    # Opex: sum both sides
    opex_credit = Opex.objects.filter(opex_filter).aggregate(total=Sum("credit"))["total"] or 0
    opex_debit  = Opex.objects.filter(opex_filter).aggregate(total=Sum("debit"))["total"]  or 0

    # NBET & MO
    nbet_cost = NBETInvoice.objects.filter(invoice_window).aggregate(total=Sum("amount"))["total"] or 0
    mo_cost   = MOInvoice.objects.filter(invoice_window).aggregate(total=Sum("amount"))["total"] or 0

    # Salaries
    salary_cost = SalaryPayment.objects.filter(salary_filter).aggregate(total=Sum("amount"))["total"] or 0

    total_cost = float(nbet_cost + mo_cost + opex_credit + opex_debit + salary_cost)

    # ─── 5) OPEX BREAKDOWN + DELTAS ───────────────────────────────────────────
    # We already have these filters:
    #   opex_filter     → for the selected window (year or specific month)
    #   commercial_filter / salary_filter etc.
    # We'll need previous-month filters if month is provided.

    # Determine previous-period filters
    if month:
        # we have start/end defined above
        prev_start = start - relativedelta(months=1)
        prev_end   = start
        opex_prev_filter = Q(date__gte=prev_start, date__lt=prev_end)
        # apply same geography constraints
        if district_name:
            opex_prev_filter &= Q(district__name__iexact=district_name)
        elif state_name:
            opex_prev_filter &= Q(district__state__name__iexact=state_name)
    else:
        opex_prev_filter = None

    # Querysets for current period
    qs_all    = Opex.objects.filter(opex_filter)
    qs_hq     = qs_all.filter(debit__gt=0)
    qs_non_hq = qs_all.filter(credit__gt=0)

    # Querysets for previous period (if applicable)
    if opex_prev_filter is not None:
        qs_all_prev    = Opex.objects.filter(opex_prev_filter)
        qs_hq_prev     = qs_all_prev.filter(debit__gt=0)
        qs_non_hq_prev = qs_all_prev.filter(credit__gt=0)
    else:
        qs_all_prev = qs_hq_prev = qs_non_hq_prev = None

    def breakdown_with_delta(qs_current, qs_previous, field):
        """
        Returns list of {category, amount, delta}
        where delta = % change vs. previous period.
        """
        # current totals by category
        curr = {
            row["opex_category__name"] or "Uncategorized":
            row["total"] or 0
            for row in qs_current
                .values("opex_category__name")
                .annotate(total=Sum(field))
        }
        # previous totals
        prev = {}
        if qs_previous is not None:
            prev = {
                row["opex_category__name"] or "Uncategorized":
                row["total"] or 0
                for row in qs_previous
                    .values("opex_category__name")
                    .annotate(total=Sum(field))
            }

        result = []
        for category, amt in curr.items():
            p = prev.get(category, 0)
            if p:
                delta = round(((amt - p) / p) * 100, 2)
            else:
                # no prior data → undefined or treat as 0
                delta = None
            result.append({
                "category": category,
                "amount": float(amt),
                "delta": delta,
            })
        return result

    opex_breakdown = {
        "all":    breakdown_with_delta(qs_all,    qs_all_prev,    "debit") 
                + breakdown_with_delta(qs_all,    qs_all_prev,    "credit"),
        "hq":     breakdown_with_delta(qs_hq,     qs_hq_prev,     "debit"),
        "non_hq": breakdown_with_delta(qs_non_hq, qs_non_hq_prev, "credit"),
    }


    # ─── 6) COLLECTIONS BY VENDOR ──────────────────────────────────────────────
    cv = (
        DailyCollection.objects
        .filter(date__gte=start, date__lt=end)  # uses daily .date
        .values("vendor_name")
        .annotate(amount=Sum("amount"))
    )
    collections_by_vendor = [
        {"vendor": row["vendor_name"], "amount": float(row["amount"] or 0)}
        for row in cv
    ] or [{"vendor": "Cash", "amount": revenue_collected}]

    # ─── 7) HISTORICAL SERIES (4 MONTHS) ───────────────────────────────────────
    sel_m = int(request.query_params.get("month", date.today().month))
    sel_dt = date(year, sel_m, 1)
    # last 4 periods including selected
    periods = [sel_dt - relativedelta(months=i) for i in range(3, -1, -1)]

    hist_costs = []
    hist_tariffs = []

    for dt in periods:
        # window
        win = (date(dt.year, dt.month, 1), date(dt.year, dt.month, 1) + relativedelta(months=1))

        # –– COST by type
        nc = NBETInvoice.objects.filter(month__gte=win[0], month__lt=win[1]).aggregate(t=Sum("amount"))["t"] or 0
        mc = MOInvoice.objects.filter(month__gte=win[0], month__lt=win[1]).aggregate(t=Sum("amount"))["t"] or 0
        sc = SalaryPayment.objects.filter(month__gte=win[0], month__lt=win[1]).aggregate(t=Sum("amount"))["t"] or 0
        oc = Opex.objects.filter(date__gte=win[0], date__lt=win[1]).aggregate(
            debit=Sum("debit"), credit=Sum("credit")
        )
        hist_costs.append({
            "month": dt.strftime("%b"),
            "nbet": float(nc),
            "mo":    float(mc),
            "salaries": float(sc),
            "opex_debit": float(oc["debit"]  or 0),
            "opex_credit": float(oc["credit"] or 0),
        })

        # –– TARIFFS
        # energy delivered for that month
        ed = FeederEnergyMonthly.objects.filter(period=win[0]).aggregate(t=Sum("energy_mwh"))["t"] or 0
        # commercial sums
        com = MonthlyCommercialSummary.objects.filter(
            Q(month__gte=win[0], month__lt=win[1])
        ).aggregate(b=Sum("revenue_billed"), c=Sum("revenue_collected"))
        rb = com["b"] or 0
        rc = com["c"] or 0

        billing_tr   = (rb / ed) if ed else 0
        collection_tr= (rc / ed) if ed else 0
        loss_tr      = billing_tr - collection_tr

        # find latest MYTO tariff in effect
        myto_obj = (
            MYTOTariff.objects
            .filter(effective_date__lte=win[0])
            .order_by("-effective_date")
            .first()
        )
        myto_rate = myto_obj.rate_per_kwh if myto_obj else 0

        hist_tariffs.append({
            "month": dt.strftime("%b"),
            "myto_tariff":      float(myto_rate),
            "billing_tariff":   round(billing_tr, 2),
            "collection_tariff":round(collection_tr, 2),
            "tariff_loss":      round(loss_tr, 2),
        })

    # ─── 8) BUILD RESPONSE ─────────────────────────────────────────────────────
    return Response({
        "monthly_summary":       monthly_summary,
        "revenue_billed":        revenue_billed,
        "revenue_collected":     revenue_collected,
        "total_cost":            total_cost,
        "opex_breakdown":        opex_breakdown,
        "collections_by_vendor": collections_by_vendor,
        "historical_costs":      hist_costs,
        "historical_tariffs":    hist_tariffs,
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



class FinancialAllStatesView(APIView):
    def get(self, request):
        year = int(request.GET.get("year"))
        month = int(request.GET.get("month"))
        target_month = date(year, month, 1)

        results = []

        for state in State.objects.all():
            # --- Total Cost (from Expenses) ---
            expense_total = Opex.objects.filter(
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
            cost = Opex.objects.filter(
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
            total_cost = Opex.objects.filter(
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


@api_view(['GET'])
def financial_transformer_view(request):
    feeder_slug = request.GET.get("feeder")
    mode = request.GET.get("mode", "monthly")
    year = request.GET.get("year")
    month = request.GET.get("month")

    if not feeder_slug:
        return Response({"error": "Missing feeder slug."}, status=400)

    try:
        feeder = Feeder.objects.get(slug=feeder_slug)
    except Feeder.DoesNotExist:
        return Response({"error": "Feeder not found."}, status=404)

    # Handle date filters
    if mode == "monthly" and year and month:
        year = int(year)
        month = int(month)
        start_day = date(year, month, 1)
        end_day = date(year, month, monthrange(year, month)[1])
        date_from, date_to = start_day, end_day
    else:
        date_from, date_to = get_date_range_from_request(request, "date")

    transformer_data = []
    for transformer in feeder.transformers.all():
        reps = SalesRepresentative.objects.filter(
            assigned_transformers=transformer
        ).distinct()

        summary = MonthlyCommercialSummary.objects.filter(
            sales_rep__in=reps,
            month__range=(date_from, date_to)
        ).aggregate(
            revenue_billed=Sum("revenue_billed"),
            revenue_collected=Sum("revenue_collected")
        )

        revenue_billed = summary["revenue_billed"] or 0
        revenue_collected = summary["revenue_collected"] or 0

        total_cost = Opex.objects.filter(
            district=feeder.business_district,
            date__range=(date_from, date_to)
        ).aggregate(total=Sum("credit"))["total"] or 0

        transformer_data.append({
            "transformer": transformer.name,
            "slug": transformer.slug,
            "total_cost": round(total_cost, 2),
            "revenue_billed": round(revenue_billed, 2),
            "revenue_collected": round(revenue_collected, 2),
            "atcc": 6
        })

    return Response({
        "feeder": feeder.name,
        "slug": feeder.slug,
        "transformers": transformer_data
    })
