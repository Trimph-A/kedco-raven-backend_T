from django.db.models import Sum
from commercial.date_filters import get_date_range_from_request
from commercial.utils import get_filtered_feeders
from commercial.models import *


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
        qs = qs.filter(sales_rep__assigned_feeders__slug=feeder_slug)

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