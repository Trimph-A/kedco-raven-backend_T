from django.db.models import Sum
from commercial.date_filters import get_date_range_from_request
from commercial.utils import get_filtered_feeders
from commercial.models import *

def calculate_derived_metrics(request):
    # Filters
    date_from, date_to = get_date_range_from_request(request, 'date')
    month_from, month_to = get_date_range_from_request(request, 'month')
    feeders = get_filtered_feeders(request)

    # Aggregate all relevant data
    revenue_collected = DailyRevenueCollected.objects.filter(
        feeder__in=feeders,
        date__range=(date_from, date_to)
    ).aggregate(total=Sum('amount'))['total'] or 0

    revenue_billed = MonthlyRevenueBilled.objects.filter(
        feeder__in=feeders,
        month__range=(month_from, month_to)
    ).aggregate(total=Sum('amount'))['total'] or 0

    energy_billed = MonthlyEnergyBilled.objects.filter(
        feeder__in=feeders,
        month__range=(month_from, month_to)
    ).aggregate(total=Sum('energy_mwh'))['total'] or 0

    energy_delivered = DailyEnergyDelivered.objects.filter(
        feeder__in=feeders,
        date__range=(date_from, date_to)
    ).aggregate(total=Sum('energy_mwh'))['total'] or 0

    customer_stats = MonthlyCustomerStats.objects.filter(
        feeder__in=feeders,
        month__range=(month_from, month_to)
    ).aggregate(
        customers_billed=Sum('customers_billed'),
        customer_response_count=Sum('customer_response_count')
    )

    # Compute derived metrics
    collection_eff = (revenue_collected / revenue_billed) * 100 if revenue_billed else 0
    billing_eff = (energy_billed / energy_delivered) * 100 if energy_delivered else 0
    atc_c = 100 - (billing_eff * collection_eff / 100) if billing_eff and collection_eff else 100
    energy_collected = (collection_eff / 100) * energy_billed
    response_rate = (
        (customer_stats['customer_response_count'] / customer_stats['customers_billed']) * 100
        if customer_stats['customers_billed'] else 0
    )

    return {
        "filters_applied": {
            "date_from": str(date_from) if date_from else None,
            "date_to": str(date_to) if date_to else None,
            "month_from": str(month_from) if month_from else None,
            "month_to": str(month_to) if month_to else None,
        },
        "raw_totals": {
            "revenue_collected": revenue_collected,
            "revenue_billed": revenue_billed,
            "energy_billed": energy_billed,
            "energy_delivered": energy_delivered,
        },
        "metrics": {
            "collection_efficiency": round(collection_eff, 2),
            "billing_efficiency": round(billing_eff, 2),
            "energy_collected": round(energy_collected, 2),
            "atc_c": round(atc_c, 2),
            "customer_response_rate": round(response_rate, 2),
        }
    }
