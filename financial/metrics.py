from django.db.models import Sum
from commercial.utils import get_filtered_feeders
from commercial.date_filters import get_date_range_from_request
from financial.models import *

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


def get_total_collections(request):
    feeders = get_filtered_feeders(request)
    date_from, date_to = get_date_range_from_request(request, 'date')

    qs = DailyCollection.objects.filter(feeder__in=feeders)

    if date_from and date_to:
        qs = qs.filter(date__range=(date_from, date_to))
    elif date_from:
        qs = qs.filter(date__gte=date_from)
    elif date_to:
        qs = qs.filter(date__lte=date_to)

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


def get_sales_rep_performance_summary(request):
    sales_rep_slug = request.GET.get('sales_rep')
    feeder_slug = request.GET.get('feeder')
    month_from, month_to = get_date_range_from_request(request, 'month')

    qs = SalesRepPerformance.objects.all()

    if sales_rep_slug:
        qs = qs.filter(sales_rep__slug=sales_rep_slug)

    if month_from and month_to:
        qs = qs.filter(month__range=(month_from, month_to))
    elif month_from:
        qs = qs.filter(month__gte=month_from)
    elif month_to:
        qs = qs.filter(month__lte=month_to)

    if feeder_slug:
        qs = qs.filter(sales_rep__assigned_feeders__slug=transformer_slug)

    summary = qs.aggregate(
        total_outstanding_billed=Sum('outstanding_billed'),
        total_current_billed=Sum('current_billed'),
        total_collections=Sum('collections'),
        total_daily_run_rate=Sum('daily_run_rate'),
        total_collections_on_outstanding=Sum('collections_on_outstanding'),
        total_active_accounts=Sum('active_accounts'),
        total_suspended_accounts=Sum('suspended_accounts'),
    )

    return {key: round(value, 2) if isinstance(value, float) else (value or 0) for key, value in summary.items()}



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
