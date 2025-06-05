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



from common.models import Feeder
from django.db.models import Q
from .models import HourlyLoad, FeederInterruption
from datetime import timedelta

def get_feeder_availability_summary(month=None, year=None, from_date=None, to_date=None, state=None, business_district=None):
    load_filters = Q()
    if month and year:
        load_filters &= Q(date__month=month, date__year=year)
    elif from_date and to_date:
        load_filters &= Q(date__range=[from_date, to_date])

    interruption_filters = Q()
    if month and year:
        interruption_filters &= Q(occurred_at__month=month, occurred_at__year=year)
    elif from_date and to_date:
        interruption_filters &= Q(occurred_at__date__range=[from_date, to_date])

    if business_district:
        feeders = Feeder.objects.filter(business_district__name=business_district)
    elif state:
        feeders = Feeder.objects.filter(business_district__state__name=state)
    else:
        feeders = Feeder.objects.all()

    result = []
    for feeder in feeders:
        load_data = HourlyLoad.objects.filter(feeder=feeder).filter(load_filters)
        interruption_data = FeederInterruption.objects.filter(feeder=feeder).filter(interruption_filters)

        # Compute daily hours with load > 0
        daily_hours = {}
        for entry in load_data:
            if entry.load_mw > 0:
                daily_hours.setdefault(entry.date, 0)
                daily_hours[entry.date] += 1

        if daily_hours:
            avg_supply = round(sum(daily_hours.values()) / len(daily_hours), 2)
        else:
            avg_supply = 0

        # Compute duration and turnaround manually
        durations = []
        for i in interruption_data:
            if i.occurred_at and i.restored_at:
                duration = (i.restored_at - i.occurred_at).total_seconds() / 3600
                durations.append(duration)

        avg_duration = round(sum(durations) / len(durations), 2) if durations else 0
        avg_turnaround = avg_duration

        result.append({
            "feeder_name": feeder.name,
            "voltage_level": feeder.voltage_level,
            "avg_hours_of_supply": avg_supply,
            "duration_of_interruptions": avg_duration,
            "turnaround_time": avg_turnaround,
            "ftc": len(daily_hours),  # Number of tracked days
        })

    return result


