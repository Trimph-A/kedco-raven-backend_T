from rest_framework import viewsets
from .models import *
from .serializers import *
from commercial.mixins import FeederFilteredQuerySetMixin
from commercial.date_filters import get_date_range_from_request
from rest_framework.views import APIView
from rest_framework.response import Response
from technical.metrics import (
    get_average_hours_of_supply,
    get_average_interruption_duration,
    get_peak_load,
    get_top_or_bottom_loaded_feeders,
)
from django.db.models.functions import TruncMonth
from commercial.utils import get_filtered_feeders
from django.db.models import Avg



class EnergyDeliveredViewSet(viewsets.ModelViewSet):
    serializer_class = EnergyDeliveredSerializer

    def get_queryset(self):
        feeders = get_filtered_feeders(self.request)
        date_from, date_to = get_date_range_from_request(self.request, 'date')

        qs = EnergyDelivered.objects.filter(feeder__in=feeders)

        if date_from and date_to:
            qs = qs.filter(date__range=(date_from, date_to))
        elif date_from:
            qs = qs.filter(date__gte=date_from)
        elif date_to:
            qs = qs.filter(date__lte=date_to)

        return qs


class HourlyLoadViewSet(viewsets.ModelViewSet):
    serializer_class = HourlyLoadSerializer

    def get_queryset(self):
        feeders = get_filtered_feeders(self.request)
        date_from, date_to = get_date_range_from_request(self.request, 'date')

        qs = HourlyLoad.objects.filter(feeder__in=feeders)

        if date_from and date_to:
            qs = qs.filter(date__range=(date_from, date_to))
        elif date_from:
            qs = qs.filter(date__gte=date_from)
        elif date_to:
            qs = qs.filter(date__lte=date_to)

        return qs


class FeederInterruptionViewSet(viewsets.ModelViewSet):
    serializer_class = FeederInterruptionSerializer

    def get_queryset(self):
        feeders = get_filtered_feeders(self.request)
        date_from, date_to = get_date_range_from_request(self.request, 'date')

        qs = FeederInterruption.objects.filter(feeder__in=feeders)

        if date_from and date_to:
            qs = qs.filter(occurred_at__date__range=(date_from, date_to))
        elif date_from:
            qs = qs.filter(occurred_at__date__gte=date_from)
        elif date_to:
            qs = qs.filter(occurred_at__date__lte=date_to)

        return qs


class DailyHoursOfSupplyViewSet(viewsets.ModelViewSet):
    serializer_class = DailyHoursOfSupplySerializer

    def get_queryset(self):
        feeders = get_filtered_feeders(self.request)
        date_from, date_to = get_date_range_from_request(self.request, 'date')

        qs = DailyHoursOfSupply.objects.filter(feeder__in=feeders)

        if date_from and date_to:
            qs = qs.filter(date__range=(date_from, date_to))
        elif date_from:
            qs = qs.filter(date__gte=date_from)
        elif date_to:
            qs = qs.filter(date__lte=date_to)

        return qs


class TechnicalMetricsView(APIView):
    def get(self, request):
        top_n = int(request.GET.get('top_n', 5))
        bottom_n = int(request.GET.get('bottom_n', 5))

        data = {
            "average_hours_of_supply": round(get_average_hours_of_supply(request), 2),
            "average_interruption_duration": round(get_average_interruption_duration(request), 2),
            "peak_load": round(get_peak_load(request), 2),
            "top_loaded_feeders": get_top_or_bottom_loaded_feeders(request, top=True, limit=top_n),
            "least_loaded_feeders": get_top_or_bottom_loaded_feeders(request, top=False, limit=bottom_n)
        }
        return Response(data)



class TechnicalMonthlySummaryView(APIView):
    def get(self, request):
        feeders = get_filtered_feeders(request)
        date_from, date_to = get_date_range_from_request(request, 'date')

        supply_qs = DailyHoursOfSupply.objects.filter(feeder__in=feeders)
        if date_from and date_to:
            supply_qs = supply_qs.filter(date__range=(date_from, date_to))
        elif date_from:
            supply_qs = supply_qs.filter(date__gte=date_from)
        elif date_to:
            supply_qs = supply_qs.filter(date__lte=date_to)

        supply_monthly = supply_qs.annotate(month=TruncMonth('date')).values('month').annotate(
            avg_hours=Avg('hours_supplied')
        ).order_by('month')

        interruption_qs = FeederInterruption.objects.filter(feeder__in=feeders)
        if date_from and date_to:
            interruption_qs = interruption_qs.filter(occurred_at__date__range=(date_from, date_to))
        elif date_from:
            interruption_qs = interruption_qs.filter(occurred_at__date__gte=date_from)
        elif date_to:
            interruption_qs = interruption_qs.filter(occurred_at__date__lte=date_to)

        data = []
        for month in supply_monthly:
            month_date = month['month']
            avg_hours = month['avg_hours']

            inter_q = interruption_qs.filter(occurred_at__month=month_date.month, occurred_at__year=month_date.year)
            durations = [
                (i.restored_at - i.occurred_at).total_seconds() / 3600 for i in inter_q
            ]
            avg_interrupt = sum(durations) / len(durations) if durations else 0

            data.append({
                "month": month_date.strftime("%Y-%m"),
                "average_hours_of_supply": round(avg_hours, 2) if avg_hours else 0,
                "average_interruption_duration": round(avg_interrupt, 2),
            })

        return Response(data)


from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Avg, Sum, Count
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta # type: ignore

from technical.models import EnergyDelivered, HourlyLoad, FeederInterruption
from common.models import Feeder


def get_month_range(year, month):
    start = datetime(year, month, 1)
    end = start + relativedelta(months=1) - timedelta(days=1)
    return start.date(), end.date()


def delta(current, previous):
    if previous == 0:
        return 0
    return round(((current - previous) / previous) * 100, 2)


def calculate_hours_of_supply(from_date, to_date):
    hours = HourlyLoad.objects.filter(
        date__range=(from_date, to_date),
        load_mw__gt=0
    ).values('feeder', 'date').annotate(
        count=Count('hour')
    ).aggregate(avg=Avg('count'))['avg'] or 0
    return round(hours, 2)


def get_avg_interruption_duration(from_date, to_date):
    qs = FeederInterruption.objects.filter(
        occurred_at__date__range=(from_date, to_date),
        restored_at__isnull=False
    )
    total_hours = sum(i.duration_hours for i in qs)
    count = qs.count()
    return round(total_hours / count, 2) if count else 0


@api_view(["GET"])
def technical_overview_view(request):
    year = int(request.GET.get("year", datetime.now().year))
    month = int(request.GET.get("month", datetime.now().month))
    start_date, end_date = get_month_range(year, month)
    prev_dt = datetime(year, month, 1) - relativedelta(months=1)
    prev_start, prev_end = get_month_range(prev_dt.year, prev_dt.month)

    def get_avg(model, field, from_date, to_date):
        return model.objects.filter(date__range=(from_date, to_date)).aggregate(avg=Avg(field))["avg"] or 0

    def get_sum(model, field, from_date, to_date):
        return model.objects.filter(date__range=(from_date, to_date)).aggregate(total=Sum(field))["total"] or 0

    def get_metric_with_history(calc_fn):
        history = []
        for i in range(4, 0, -1):
            dt = datetime(year, month, 1) - relativedelta(months=i)
            m_start, m_end = get_month_range(dt.year, dt.month)
            value = calc_fn(m_start, m_end)
            history.append({"month": m_start.strftime("%b"), "value": value})
        current = calc_fn(start_date, end_date)
        prev = calc_fn(prev_start, prev_end)
        return {
            "current": current,
            "delta": delta(current, prev),
            "history": history[::-1]
        }

    energy_now = get_sum(EnergyDelivered, "energy_mwh", start_date, end_date)
    energy_prev = get_sum(EnergyDelivered, "energy_mwh", prev_start, prev_end)

    load_now = get_avg(HourlyLoad, "load_mw", start_date, end_date)
    load_prev = get_avg(HourlyLoad, "load_mw", prev_start, prev_end)

    interruptions_now = FeederInterruption.objects.filter(
        occurred_at__date__range=(start_date, end_date)
    ).count()
    interruptions_prev = FeederInterruption.objects.filter(
        occurred_at__date__range=(prev_start, prev_end)
    ).count()

    supply_hours = get_metric_with_history(calculate_hours_of_supply)
    interruption_duration = get_metric_with_history(get_avg_interruption_duration)
    turnaround_time = interruption_duration  # Same as requested

    feeders_now = Feeder.objects.count()
    feeders_prev = 180  # mock
    customer_count = 5_000_000  # mock

    breakdown = {
        "feeder_count": {"value": feeders_now, "delta": delta(feeders_now, feeders_prev)},
        "avg_daily_interruptions": {"value": interruptions_now, "delta": delta(interruptions_now, interruptions_prev)},
        "avg_turnaround": {"value": turnaround_time["current"], "delta": turnaround_time["delta"]},
        "customer_count": {"value": customer_count, "delta": -5}
    }

    def interruption_breakdown_for(month_offset):
        dt = datetime(year, month, 1) - relativedelta(months=month_offset)
        m_start, m_end = get_month_range(dt.year, dt.month)
        interruptions = FeederInterruption.objects.filter(
            occurred_at__date__range=(m_start, m_end)
        )
        type_totals = {}
        for itype, _ in FeederInterruption.INTERRUPTION_TYPES:
            hours = sum(
                i.duration_hours
                for i in interruptions.filter(interruption_type=itype)
                if i.restored_at
            )
            type_totals[itype] = round(hours, 2)
        return {
            "month": m_start.strftime("%B"),
            "total": round(sum(type_totals.values()), 2),
            "delta": 2.5 + month_offset,
            "breakdown": type_totals
        }

    interruptions_data = [interruption_breakdown_for(i) for i in range(4)]

    trend_series = []
    if "date" in request.GET:
        trend_date = request.GET["date"]
        trend_qs = HourlyLoad.objects.filter(date=trend_date).values('hour').annotate(
            avg_load=Avg('load_mw')
        ).order_by('hour')
        trend_series = [{"hour": entry["hour"], "value": round(entry["avg_load"], 2)} for entry in trend_qs]

    return Response({
        "highlight_metrics": {
            "energy_delivered": {"value": float(energy_now), "delta": delta(energy_now, energy_prev)},
            "average_load": {"value": float(load_now), "delta": delta(load_now, load_prev)},
            "interruptions": {"value": interruptions_now, "delta": delta(interruptions_now, interruptions_prev)},
        },
        "supply_and_quality": {
            "supply_hours": supply_hours,
            "interruption_duration": interruption_duration,
            "turnaround_time": turnaround_time
        },
        "technical_breakdown": breakdown,
        "interruption_sources": interruptions_data,
        "load_trend": {
            "unit": "MW",
            "date": request.GET.get("date"),
            "series": trend_series
        }
    })


from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Avg, Sum, Max
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta # type: ignore

from technical.models import HourlyLoad, FeederInterruption
from common.models import Feeder


def get_date_range_from_request(request):
    mode = request.GET.get("mode", "monthly")
    if mode == "range":
        try:
            from_date = datetime.strptime(request.GET["from_date"], "%Y-%m-%d").date()
            to_date = datetime.strptime(request.GET["to_date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            raise ValueError("Invalid or missing from_date or to_date for range mode")
    else:
        try:
            year = int(request.GET["year"])
            month = int(request.GET["month"])
            from_date = datetime(year, month, 1).date()
            to_date = (datetime(year, month, 1) + relativedelta(months=1) - timedelta(days=1)).date()
        except (KeyError, ValueError):
            raise ValueError("Invalid or missing year or month for monthly mode")

    return from_date, to_date


def calculate_avg_supply(from_date, to_date, feeder_ids):
    hours = HourlyLoad.objects.filter(
        date__range=(from_date, to_date), load_mw__gt=0, feeder_id__in=feeder_ids
    ).values("feeder", "date").annotate(count=Count("hour")).aggregate(avg=Avg("count"))
    return round(hours["avg"] or 0, 2)


def calculate_avg_interruption_duration(from_date, to_date, feeder_ids):
    interruptions = FeederInterruption.objects.filter(
        occurred_at__date__range=(from_date, to_date),
        restored_at__isnull=False,
        feeder_id__in=feeder_ids
    )
    total_hours = sum(i.duration_hours for i in interruptions)
    count = interruptions.count()
    return round(total_hours / count, 2) if count else 0


@api_view(["GET"])
def all_states_technical_summary(request):
    from_date, to_date = get_date_range_from_request(request)

    states = Feeder.objects.values_list("business_district__state__name", flat=True).distinct()
    overview = []

    for state in states:
        feeders = Feeder.objects.filter(business_district__state__name=state)
        feeder_ids = feeders.values_list("id", flat=True)

        avg_supply = calculate_avg_supply(from_date, to_date, feeder_ids)
        avg_duration = calculate_avg_interruption_duration(from_date, to_date, feeder_ids)
        turnaround = avg_duration  # same as duration
        ftc = 80  # placeholder

        feeder_count = feeders.count()
        peak_load = HourlyLoad.objects.filter(
            feeder_id__in=feeder_ids, date__range=(from_date, to_date)
        ).aggregate(peak=Max("load_mw"))["peak"] or 0

        customer_population = 20000 + feeder_count * 100  # mock calculation

        overview.append({
            "state": state,
            "metrics": {
                "avg_supply": avg_supply,
                "avg_duration": avg_duration,
                "turnaround": turnaround,
                "ftc": ftc,
                "feeder_count": feeder_count,
                "peak_load": peak_load,
                "customer_population": customer_population,
            }
        })

    return Response({"overview": overview})



from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Avg, Sum, Count, Max
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta # type: ignore

from technical.models import HourlyLoad, FeederInterruption, EnergyDelivered
from common.models import Feeder


def get_month_range(year, month):
    start = datetime(year, month, 1)
    end = start + relativedelta(months=1) - timedelta(days=1)
    return start.date(), end.date()


def delta(current, previous):
    if previous == 0:
        return 0
    return round(((current - previous) / previous) * 100, 2)


def get_metric_with_history(model_fn, feeder_ids, year, month):
    history = []
    for i in range(4, 0, -1):
        dt = datetime(year, month, 1) - relativedelta(months=i)
        m_start, m_end = get_month_range(dt.year, dt.month)
        val = model_fn(m_start, m_end, feeder_ids)
        history.append(round(val, 2))

    current_start, current_end = get_month_range(year, month)
    current = model_fn(current_start, current_end, feeder_ids)
    prev = model_fn(*get_month_range((datetime(year, month, 1) - relativedelta(months=1)).year, (datetime(year, month, 1) - relativedelta(months=1)).month), feeder_ids)

    return {
        "current": round(current, 2),
        "delta": delta(current, prev),
        "history": history[::-1] + [round(current, 2)]
    }


def calculate_avg_supply(from_date, to_date, feeder_ids):
    hours = HourlyLoad.objects.filter(
        date__range=(from_date, to_date), load_mw__gt=0, feeder_id__in=feeder_ids
    ).values("feeder", "date").annotate(count=Count("hour")).aggregate(avg=Avg("count"))
    return hours["avg"] or 0


def calculate_avg_interruption_duration(from_date, to_date, feeder_ids):
    interruptions = FeederInterruption.objects.filter(
        occurred_at__date__range=(from_date, to_date),
        restored_at__isnull=False,
        feeder_id__in=feeder_ids
    )
    total_hours = sum(i.duration_hours for i in interruptions)
    count = interruptions.count()
    return total_hours / count if count else 0


def calculate_interruptions(from_date, to_date, feeder_ids):
    return FeederInterruption.objects.filter(
        occurred_at__date__range=(from_date, to_date),
        feeder_id__in=feeder_ids
    ).count()


def calculate_energy_delivered(from_date, to_date, feeder_ids):
    return EnergyDelivered.objects.filter(
        date__range=(from_date, to_date),
        feeder_id__in=feeder_ids
    ).aggregate(total=Sum("energy_mwh"))['total'] or 0


def calculate_feeder_count(_, __, feeder_ids):
    return len(feeder_ids)


@api_view(["GET"])
def state_technical_summary(request):
    state_name = request.GET.get("state")
    year = int(request.GET.get("year", datetime.now().year))
    month = int(request.GET.get("month", datetime.now().month))
    day = request.GET.get("date")

    feeders = Feeder.objects.filter(business_district__state__name=state_name)
    feeder_ids = feeders.values_list("id", flat=True)

    # Top and bottom 5 peak load feeders
    month_start, month_end = get_month_range(year, month)
    peak_data = HourlyLoad.objects.filter(
        date__range=(month_start, month_end), feeder_id__in=feeder_ids
    ).values(
        "feeder__name",
        "feeder__substation__name",
        "feeder__voltage_level",
    ).annotate(
        peak=Max("load_mw")
    ).order_by("-peak")

    top_5 = peak_data[:5]
    bottom_5 = list(peak_data)[-5:]  # reverse will not work directly on queryset; cast to list first

    top_feeders = [
        {
            "feeder": i["feeder__name"],
            "substation": i["feeder__substation__name"],
            "voltage_level": i["feeder__voltage_level"],
            "peak": i["peak"],
        }
        for i in top_5
    ]
    bottom_feeders = [
        {
            "feeder": i["feeder__name"],
            "substation": i["feeder__substation__name"],
            "voltage_level": i["feeder__voltage_level"],
            "peak": i["peak"],
        }
        for i in bottom_5
    ]

    # Load trend for specific day
    trend_series = []
    if day:
        trend_qs = HourlyLoad.objects.filter(
            date=day, feeder_id__in=feeder_ids
        ).values("hour").annotate(avg=Avg("load_mw")).order_by("hour")
        trend_series = [{"hour": i["hour"], "value": round(i["avg"], 2)} for i in trend_qs]

    return Response({
        "top_feeders": top_feeders,
        "bottom_feeders": bottom_feeders,
        "load_trend": trend_series,
        "metrics": {
            "avg_supply": get_metric_with_history(calculate_avg_supply, feeder_ids, year, month),
            "avg_duration": get_metric_with_history(calculate_avg_interruption_duration, feeder_ids, year, month),
            "turnaround_time": get_metric_with_history(calculate_avg_interruption_duration, feeder_ids, year, month),
            "interruptions": get_metric_with_history(calculate_interruptions, feeder_ids, year, month),
            "energy_delivered": get_metric_with_history(calculate_energy_delivered, feeder_ids, year, month),
            "feeder_count": get_metric_with_history(calculate_feeder_count, feeder_ids, year, month),
        }
    })



from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Count, Max, Avg
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta # type: ignore

from technical.models import HourlyLoad, FeederInterruption
from common.models import Feeder


def get_date_range(request):
    mode = request.GET.get("mode", "monthly")
    if mode == "range":
        from_date = datetime.strptime(request.GET.get("from_date"), "%Y-%m-%d").date()
        to_date = datetime.strptime(request.GET.get("to_date"), "%Y-%m-%d").date()
    else:
        year = int(request.GET.get("year", datetime.today().year))
        month = int(request.GET.get("month", datetime.today().month))
        from_date = datetime(year, month, 1).date()
        to_date = (from_date + relativedelta(months=1)) - timedelta(days=1)
    return from_date, to_date


@api_view(["GET"])
def all_business_districts_technical_summary(request):
    state = request.GET.get("state")
    from_date, to_date = get_date_range(request)

    districts = Feeder.objects.filter(
        business_district__state__name=state
    ).values(
        "business_district__id",
        "business_district__name"
    ).distinct()

    response_data = []

    for district in districts:
        district_name = district["business_district__name"]
        district_id = district["business_district__id"]

        feeders = Feeder.objects.filter(business_district__id=district_id)
        feeder_ids = feeders.values_list("id", flat=True)

        # Metrics
        hours_of_supply = HourlyLoad.objects.filter(
            date__range=(from_date, to_date),
            feeder_id__in=feeder_ids,
            load_mw__gt=0
        ).values("feeder", "date").annotate(
            hours_count=Count("hour")
        ).aggregate(avg_hours=Avg("hours_count"))["avg_hours"] or 0

        interruptions = FeederInterruption.objects.filter(
            occurred_at__date__range=(from_date, to_date),
            restored_at__isnull=False,
            feeder_id__in=feeder_ids
        )

        duration = sum(i.duration_hours for i in interruptions)
        interruption_count = interruptions.count()
        avg_duration = round(duration / interruption_count, 2) if interruption_count else 0

        turnaround_time = avg_duration  
        ftc = 3000  

        feeder_count = feeders.count()

        peak_load = HourlyLoad.objects.filter(
            feeder_id__in=feeder_ids,
            date__range=(from_date, to_date)
        ).aggregate(max_load=Max("load_mw"))["max_load"] or 0

        response_data.append({
            "district": district_name,
            "metrics": {
                "avg_supply": round(hours_of_supply, 2),
                "duration": avg_duration,
                "turnaround_time": turnaround_time,
                "ftc": ftc,
                "feeder_count": feeder_count,
                "peak_load": round(peak_load, 2),
            }
        })

    return Response({"districts": response_data})





from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Avg, Count, Max
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta # type: ignore

from technical.models import HourlyLoad, FeederInterruption
from common.models import Feeder


def get_month_range(year, month):
    start = datetime(year, month, 1)
    end = (start + relativedelta(months=1)) - timedelta(days=1)
    return start.date(), end.date()


def delta(current, previous):
    if previous == 0:
        return 0
    return round(((current - previous) / previous) * 100, 2)


def get_metric_with_history(calc_fn, feeder_ids, year, month):
    history = []
    for i in range(4, 0, -1):
        dt = datetime(year, month, 1) - relativedelta(months=i)
        start, end = get_month_range(dt.year, dt.month)
        val = calc_fn(start, end, feeder_ids)
        history.append(round(val, 2))
        

    current_start, current_end = get_month_range(year, month)
    current = calc_fn(current_start, current_end, feeder_ids)

    prev_month = datetime(year, month, 1) - relativedelta(months=1)
    prev_start, prev_end = get_month_range(prev_month.year, prev_month.month)
    previous = calc_fn(prev_start, prev_end, feeder_ids)

    return {
        "current": round(current, 2),
        "delta": delta(current, previous),
        "history": history,
    }


def calculate_avg_supply(from_date, to_date, feeder_ids):
    hours = HourlyLoad.objects.filter(
        date__range=(from_date, to_date), feeder_id__in=feeder_ids, load_mw__gt=0
    ).values("feeder", "date").annotate(hour_count=Count("hour")).aggregate(avg=Avg("hour_count"))
    return hours["avg"] or 0


def calculate_avg_interruption_duration(from_date, to_date, feeder_ids):
    interruptions = FeederInterruption.objects.filter(
        occurred_at__date__range=(from_date, to_date),
        restored_at__isnull=False,
        feeder_id__in=feeder_ids
    )
    total_duration = sum(i.duration_hours for i in interruptions)
    return total_duration / interruptions.count() if interruptions.exists() else 0


def calculate_avg_interruptions(from_date, to_date, feeder_ids):
    days = (to_date - from_date).days or 1
    total = FeederInterruption.objects.filter(
        occurred_at__date__range=(from_date, to_date),
        feeder_id__in=feeder_ids
    ).count()
    return total / days


def calculate_faults(from_date, to_date, feeder_ids):
    return FeederInterruption.objects.filter(
        occurred_at__date__range=(from_date, to_date),
        feeder_id__in=feeder_ids
    ).count()


def calculate_feeder_count(_, __, feeder_ids):
    return len(feeder_ids)


@api_view(["GET"])
def business_district_technical_summary(request):
    district = request.GET.get("district")
    year = int(request.GET.get("year", datetime.now().year))
    month = int(request.GET.get("month", datetime.now().month))

    feeders = Feeder.objects.filter(business_district__name=district)
    feeder_ids = feeders.values_list("id", flat=True)

    start_date, end_date = get_month_range(year, month)

    # Top & Bottom Peak Feeders
    peak_queryset = HourlyLoad.objects.filter(
        date__range=(start_date, end_date),
        feeder_id__in=feeder_ids
    ).values(
        "feeder__name", "feeder__voltage_level"
    ).annotate(peak=Max("load_mw")).order_by("-peak")

    top_feeders = [
        {
            "feeder": obj["feeder__name"],
            "voltage_level": obj["feeder__voltage_level"],
            "peak": obj["peak"]
        } for obj in peak_queryset[:5]
    ]

    bottom_feeders = [
        {
            "feeder": obj["feeder__name"],
            "voltage_level": obj["feeder__voltage_level"],
            "peak": obj["peak"]
        } for obj in list(peak_queryset.reverse())[:5]
    ]

    return Response({
        "metrics": {
            "avg_supply": get_metric_with_history(calculate_avg_supply, feeder_ids, year, month),
            "duration": get_metric_with_history(calculate_avg_interruption_duration, feeder_ids, year, month),
            "turnaround_time": get_metric_with_history(calculate_avg_interruption_duration, feeder_ids, year, month),
            "interruptions": get_metric_with_history(calculate_avg_interruptions, feeder_ids, year, month),
            "faults": get_metric_with_history(calculate_faults, feeder_ids, year, month),
            "feeder_count": get_metric_with_history(calculate_feeder_count, feeder_ids, year, month),
        },
        "top_feeders": top_feeders,
        "bottom_feeders": bottom_feeders
    })


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .metrics import get_feeder_availability_summary
from .serializers import FeederAvailabilitySerializer

class FeederAvailabilityOverview(APIView):

    def get(self, request):
        month = request.GET.get("month")
        year = request.GET.get("year")
        from_date = request.GET.get("from_date")
        to_date = request.GET.get("to_date")
        state = request.GET.get("state")
        business_district = request.GET.get("business_district")

        data = get_feeder_availability_summary(
            month=month,
            year=year,
            from_date=from_date,
            to_date=to_date,
            state=state,
            business_district=business_district,
        )

        serializer = FeederAvailabilitySerializer(data, many=True)
        return Response(serializer.data)




from rest_framework.decorators import api_view
from rest_framework.response import Response
from datetime import datetime
from django.db.models import Avg, Count
from common.models import Feeder
from commercial.models import SalesRepresentative
from technical.models import EnergyDelivered


@api_view(["GET"])
def service_band_technical_metrics(request):
    state = request.GET.get("state")
    year = int(request.GET.get("year", datetime.now().year))
    month = int(request.GET.get("month", datetime.now().month))

    # Get feeders with bands and optional state filtering
    feeders = Feeder.objects.filter(band__isnull=False)
    if state:
        feeders = feeders.filter(business_district__state__name=state)

    date_from, date_to = get_month_range(year, month)

    results = {}

    for band in feeders.values_list("band__name", flat=True).distinct():
        band_feeders = feeders.filter(band__name=band)
        feeder_ids = band_feeders.values_list("id", flat=True)

        # Simulated metrics
        feeder_count = band_feeders.count()

        sales_reps = SalesRepresentative.objects.filter(
            assigned_transformers__feeder__in=feeder_ids
        ).distinct()
        customer_count = sales_reps.count() * 100  # Simulated

        avg_peak_load = round(
            EnergyDelivered.objects.filter(
                feeder__in=feeder_ids,
                date__range=(date_from, date_to)
            ).aggregate(avg=Avg("energy_mwh"))["avg"] or 0, 2
        )

        duration_of_interruption = 20 + hash(band) % 10  # Simulated
        turnaround_time = 10 + hash(band[::-1]) % 15  # Simulated

        results[band] = {
            "feeder_count": feeder_count,
            "customer_count": customer_count,
            "avg_peak_load": avg_peak_load,
            "duration_of_interruption": duration_of_interruption,
            "turnaround_time": turnaround_time,
        }

    return Response({"results": results})
