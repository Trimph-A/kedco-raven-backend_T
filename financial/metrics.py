from django.db.models import Sum
from commercial.utils import get_filtered_feeders
from commercial.date_filters import get_date_range_from_request
from financial.models import *
from commercial.models import MonthlyCommercialSummary

def get_total_cost(request):
    feeders = get_filtered_feeders(request)
    month_from, month_to = get_date_range_from_request(request, 'month')

    qs = Expense.objects.filter(feeder__in=feeders) if feeders.exists() else Expense.objects.all()

    if month_from and month_to:
        qs = qs.filter(month__range=(month_from, month_to))
    elif month_from:
        qs = qs.filter(month__gte=month_from)
    elif month_to:
        qs = qs.filter(month__lte=month_to)

    return qs.aggregate(total=Sum('amount'))['total'] or 0


def get_total_revenue_billed(request):
    feeders = get_filtered_feeders(request)
    month_from, month_to = get_date_range_from_request(request, 'month')

    qs = MonthlyRevenueBilled.objects.filter(feeder__in=feeders)

    if month_from and month_to:
        qs = qs.filter(month__range=(month_from, month_to))
    elif month_from:
        qs = qs.filter(month__gte=month_from)
    elif month_to:
        qs = qs.filter(month__lte=month_to)

    return qs.aggregate(total=Sum('amount'))['total'] or 0



def get_opex_breakdown(request):
    feeders = get_filtered_feeders(request)
    month_from, month_to = get_date_range_from_request(request, 'month')

    qs = Expense.objects.filter(feeder__in=feeders) if feeders.exists() else Expense.objects.all()

    if month_from and month_to:
        qs = qs.filter(month__range=(month_from, month_to))
    elif month_from:
        qs = qs.filter(month__gte=month_from)
    elif month_to:
        qs = qs.filter(month__lte=month_to)

    breakdown = qs.values('category__name').annotate(total=Sum('amount')).order_by('-total')

    return list(breakdown)


def get_tariff_loss(request):
    # MYTO allowed tariff and actual collected tariff will be modeled separately in future
    # Placeholder for now
    myto_allowed_tariff = 100  # Simulated value 
    actual_collected_tariff = 80  # Simulated value

    tariff_loss = 1 - (actual_collected_tariff / myto_allowed_tariff)
    return round(tariff_loss * 100, 2)  # As a percentage




def get_financial_summary(request):
    district = request.GET.get('district')
    state = request.GET.get('state')
    month_from, month_to = get_date_range_from_request(request, 'month')

    qs = Expense.objects.all()
    if state:
        qs = qs.filter(district__state__slug=state)
    if district:
        qs = qs.filter(district__slug=district)
    if month_from and month_to:
        qs = qs.filter(date__range=(month_from, month_to))

    total_expense = qs.aggregate(total=Sum('credit'))['total'] or 0
    total_disbursed = qs.aggregate(total=Sum('debit'))['total'] or 0

    opex_breakdown = qs.values('opex_category__name').annotate(
        total=Sum('credit')
    ).order_by('-total')

    return {
        "total_expense": total_expense,
        "hq_disbursement": total_disbursed,
        "opex_breakdown": list(opex_breakdown)
    }


from django.db.models import Sum
from commercial.models import MonthlyRevenueBilled, DailyRevenueCollected
from common.models import Feeder
from datetime import date
from calendar import monthrange

def get_financial_feeder_data(request):
    state = request.GET.get("state")
    bd = request.GET.get("business_district")
    mode = request.GET.get("mode", "monthly")  # Default to 'monthly'
    year = request.GET.get("year")
    month = request.GET.get("month")

    # Handle date filtering
    if mode == "monthly" and year and month:
        year = int(year)
        month = int(month)
        start_day = date(year, month, 1)
        end_day = date(year, month, monthrange(year, month)[1])
        date_from, date_to = start_day, end_day
    else:
        date_from, date_to = get_date_range_from_request(request, "date")

    # Apply filtering hierarchy: Business District > State
    feeders = Feeder.objects.all()
    if bd:
        feeders = feeders.filter(business_district__name=bd)
    elif state:
        feeders = feeders.filter(business_district__state__name=state)

    data = []

    for feeder in feeders:
        # Get sales reps linked to this feeder
        sales_reps = feeder.salesrepresentative_set.all()

        # Aggregate commercial summary
        summary = MonthlyCommercialSummary.objects.filter(
            sales_rep__in=sales_reps,
            month__range=(date_from, date_to)
        ).aggregate(
            revenue_billed=Sum("revenue_billed"),
            revenue_collected=Sum("revenue_collected")
        )

        revenue_billed = summary["revenue_billed"] or 0
        revenue_collected = summary["revenue_collected"] or 0

        # Aggregate cost from expenses in feeder's business district
        total_cost = Expense.objects.filter(
            district=feeder.business_district,
            date__range=(date_from, date_to)
        ).aggregate(total=Sum("credit"))["total"] or 0

        data.append({
            "feeder": feeder.name,
            "total_cost": round(total_cost, 2),
            "revenue_billed": round(revenue_billed, 2),
            "revenue_collected": round(revenue_collected, 2),
        })

    return data