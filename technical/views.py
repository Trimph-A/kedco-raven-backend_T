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
