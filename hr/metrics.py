from datetime import date, timedelta
from django.db.models import Count, Avg, Q
from hr.models import Staff
from commercial.date_filters import get_date_range_from_request

def get_hr_summary(request):
    state = request.GET.get('state')
    district = request.GET.get('district')

    # Time filters
    month_from, month_to = get_date_range_from_request(request, 'month')
    today = date.today()

    qs = Staff.objects.all()

    if state:
        qs = qs.filter(state__slug=state)
    if district:
        qs = qs.filter(district__slug=district)

    if month_from and month_to:
        qs = qs.filter(hire_date__lte=month_to)
    elif month_from:
        qs = qs.filter(hire_date__gte=month_from)
    elif month_to:
        qs = qs.filter(hire_date__lte=month_to)

    active_qs = qs.filter(exit_date__isnull=True)

    # Previous period: compare to same length before month_from
    previous_qs = Staff.objects.all()
    if month_from and month_to:
        delta = month_to - month_from
        prev_start = month_from - delta - timedelta(days=1)
        prev_end = month_from - timedelta(days=1)
        previous_qs = previous_qs.filter(hire_date__lte=prev_end)

    return {
        "total_staff": qs.count(),
        "active_staff": active_qs.count(),
        "avg_salary": round(qs.aggregate(avg=Avg("salary"))["avg"] or 0, 2),
        "avg_age": round(qs.aggregate(avg=Avg("birth_date"))["avg"] and (
            (today - qs.aggregate(avg=Avg("birth_date"))["avg"]).days // 365
        ) or 0),

        "staff_by_department": list(
            qs.values("department__name").annotate(count=Count("id")).order_by("-count")
        ),
        "staff_by_role": list(
            qs.values("role__title").annotate(count=Count("id")).order_by("-count")
        ),
        "gender_distribution": list(
            qs.values("gender").annotate(count=Count("id"))
        ),

        "retention_rate": round((
            active_qs.count() / qs.count() * 100 if qs.count() else 0
        ), 2),
        "turnover_rate": round((
            qs.filter(exit_date__range=(month_from, month_to)).count() / qs.count() * 100
            if month_from and month_to and qs.count() else 0
        ), 2),

        "staff_change_vs_previous": qs.count() - previous_qs.count() if month_from and month_to else None
    }
