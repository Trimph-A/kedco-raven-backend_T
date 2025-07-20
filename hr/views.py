# hr/views.py
from rest_framework import viewsets
from .models import Department, Role, Staff
from .serializers import DepartmentSerializer, RoleSerializer, StaffSerializer
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from rest_framework.views import APIView
from rest_framework.response import Response
from hr.metrics import get_hr_summary
from common.utils.filters import get_month_range_from_request
from django.db.models import Avg, Count, Sum, Q
from datetime import date
from common.models import State
from commercial.models import DailyCollection
from common.utils.filters import get_month_range_from_request
from django.shortcuts import get_object_or_404
from commercial.models import MonthlyCommercialSummary



class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    filter_backends = [SearchFilter]
    search_fields = ['name', 'slug']


class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    filter_backends = [SearchFilter]
    search_fields = ['title', 'slug', 'department__name']


class StaffViewSet(viewsets.ModelViewSet):
    queryset = Staff.objects.all()
    serializer_class = StaffSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    # filterset_fields = [
    #     'department', 'role', 'state', 'district', 'gender', 'grade', 'is_active'
    # ]
    filterset_fields = [
        'department', 'role', 'state', 'district', 'gender', 'grade',
    ]
    search_fields = ['full_name', 'email', 'phone_number']


class HRMetricsSummaryView(APIView):
    def get(self, request):
        data = get_hr_summary(request)
        return Response(data)


class StaffSummaryView(APIView):

    def get(self, request):
        def calculate_age(birth_date):
            today = date.today()
            return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

        # Date filter based on Ribbon
        from_date, to_date = get_month_range_from_request(request)
        queryset = Staff.objects.filter(hire_date__lte=to_date)

        total_count = queryset.count()
        avg_salary = queryset.aggregate(avg_salary=Avg("salary"))["avg_salary"] or 0

        # Age calculation
        ages = [calculate_age(staff.birth_date) for staff in queryset if staff.birth_date]
        avg_age = round(sum(ages) / len(ages)) if ages else 0

        # Retention & Turnover
        retained_count = queryset.filter(exit_date__isnull=True).count()
        exited_count = queryset.filter(exit_date__isnull=False).count()
        retention_rate = (retained_count / total_count * 100) if total_count else 0
        turnover_rate = (exited_count / total_count * 100) if total_count else 0

        distribution = queryset.values("department__name").annotate(count=Count("id"))
        gender_split = queryset.values("gender").annotate(count=Count("id"))

        return Response({
            "total_staff": total_count,
            "avg_salary": round(avg_salary),
            "avg_age": avg_age,
            "retention_rate": round(retention_rate, 2),
            "turnover_rate": round(turnover_rate, 2),
            "distribution": distribution,
            "gender_split": gender_split,
        })


class StaffStateOverviewView(APIView):
    def get(self, request):
        from_date, to_date = get_month_range_from_request(request)

        states = State.objects.all()
        results = []

        for state in states:
            staff_qs = Staff.objects.filter(state=state, hire_date__lte=to_date)
            active_staff = staff_qs.filter(Q(exit_date__isnull=True) | Q(exit_date__gt=to_date))
            exited_staff = staff_qs.filter(exit_date__range=(from_date, to_date))

            total_staff = staff_qs.count()
            active_count = active_staff.count()
            exited_count = exited_staff.count()

            # Retention & Turnover
            retention_rate = round((active_count / total_staff) * 100, 2) if total_staff else 0
            turnover_rate = round((exited_count / total_staff) * 100, 2) if total_staff else 0

            # Collections per staff

            # total_collection = DailyCollection.objects.filter(
            #     sales_rep__assigned_feeders__substation__district__state__name=state,
            #     date__range=(from_date, to_date)
            # ).aggregate(total=Sum('amount'))['total'] or 0

            total_collection = MonthlyCommercialSummary.objects.filter(
                sales_rep__assigned_feeders__business_district__state__name=state,
                month__range=(from_date, to_date)
            ).aggregate(total=Sum('revenue_collected'))['total'] or 0


            collections_per_staff = round(total_collection / active_count) if active_count else 0

            # Gender distribution
            gender_dist = (
                staff_qs.values('gender')
                .annotate(count=Count('id'))
                .order_by('gender')
            )

            # Department distribution
            dept_dist = (
                staff_qs.values("department__name")
                .annotate(count=Count("id"))
                .order_by("department__name")
            )

            results.append({
                "state": state.name,
                "slug": state.slug,
                "retention_rate": retention_rate,
                "turnover_rate": turnover_rate,
                "collections_per_staff": collections_per_staff,
                "gender_distribution": gender_dist,
                "department_distribution": dept_dist,
            })

        return Response(results)


class StaffStateDetailView(APIView):
    def get(self, request, slug):
        from_date, to_date = get_month_range_from_request(request)
        state = get_object_or_404(State, slug=slug)

        staff_qs = Staff.objects.filter(state=state, hire_date__lte=to_date)
        active_staff = staff_qs.filter(Q(exit_date__isnull=True) | Q(exit_date__gt=to_date))
        exited_staff = staff_qs.filter(exit_date__range=(from_date, to_date))

        total_staff = staff_qs.count()
        active_count = active_staff.count()
        exited_count = exited_staff.count()

        retention_rate = round((active_count / total_staff) * 100, 2) if total_staff else 0
        turnover_rate = round((exited_count / total_staff) * 100, 2) if total_staff else 0

        total_collection = DailyCollection.objects.filter(
            district__state=state,
            date__range=(from_date, to_date)
        ).aggregate(total=Sum('amount'))['total'] or 0

        collections_per_staff = round(total_collection / active_count) if active_count else 0

        gender_split = staff_qs.values("gender").annotate(count=Count("id"))
        department_split = staff_qs.values("department__name").annotate(count=Count("id"))

        return Response({
            "state": state.name,
            "slug": state.slug,
            "total_staff": total_staff,
            "collections_per_staff": collections_per_staff,
            "retention_rate": retention_rate,
            "turnover_rate": turnover_rate,
            "gender_distribution": gender_split,
            "department_distribution": department_split
        })
