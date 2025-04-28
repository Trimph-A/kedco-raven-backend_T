from django.db.models import Avg, Max, Min, Count, Sum
from commercial.utils import get_filtered_feeders
from commercial.date_filters import get_date_range_from_request
from .models import *


def get_average_hours_of_supply(request):
    feeders = get_filtered_feeders(request)
    date_from, date_to = get_date_range_from_request(request, 'date')

    qs = DailyHoursOfSupply.objects.filter(feeder__in=feeders)
    if date_from and date_to:
        qs = qs.filter(date__range=(date_from, date_to))
    elif date_from:
        qs = qs.filter(date__gte=date_from)
    elif date_to:
        qs = qs.filter(date__lte=date_to)

    return qs.aggregate(avg=Avg('hours_supplied'))['avg'] or 0


def get_average_interruption_duration(request):
    feeders = get_filtered_feeders(request)
    date_from, date_to = get_date_range_from_request(request, 'date')

    qs = FeederInterruption.objects.filter(feeder__in=feeders)
    if date_from and date_to:
        qs = qs.filter(occurred_at__date__range=(date_from, date_to))
    elif date_from:
        qs = qs.filter(occurred_at__date__gte=date_from)
    elif date_to:
        qs = qs.filter(occurred_at__date__lte=date_to)

    durations = [(i.restored_at - i.occurred_at).total_seconds() / 3600 for i in qs]
    return sum(durations) / len(durations) if durations else 0


def get_peak_load(request):
    feeders = get_filtered_feeders(request)
    date_from, date_to = get_date_range_from_request(request, 'date')

    qs = HourlyLoad.objects.filter(feeder__in=feeders)
    if date_from and date_to:
        qs = qs.filter(date__range=(date_from, date_to))
    elif date_from:
        qs = qs.filter(date__gte=date_from)
    elif date_to:
        qs = qs.filter(date__lte=date_to)

    return qs.aggregate(peak=Max('load_mw'))['peak'] or 0


def get_top_or_bottom_loaded_feeders(request, top=True, limit=5):
    feeders = get_filtered_feeders(request)
    date_from, date_to = get_date_range_from_request(request, 'date')

    qs = HourlyLoad.objects.filter(feeder__in=feeders)
    if date_from and date_to:
        qs = qs.filter(date__range=(date_from, date_to))
    elif date_from:
        qs = qs.filter(date__gte=date_from)
    elif date_to:
        qs = qs.filter(date__lte=date_to)

    agg = qs.values('feeder__slug', 'feeder__name').annotate(
        peak_load=Max('load_mw')
    ).order_by('-peak_load' if top else 'peak_load')[:limit]

    return list(agg)
