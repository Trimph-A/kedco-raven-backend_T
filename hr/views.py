from rest_framework import viewsets
from .models import Department, Role, Staff
from .serializers import DepartmentSerializer, RoleSerializer, StaffSerializer
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from rest_framework.views import APIView
from rest_framework.response import Response
from hr.metrics import get_hr_summary
from common.utils.filters import get_month_range_from_request
from django.db.models import Avg, Count, Sum



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
    filterset_fields = [
        'department', 'role', 'state', 'district', 'gender', 'grade', 'is_active'
    ]
    search_fields = ['full_name', 'email', 'phone_number']


class HRMetricsSummaryView(APIView):
    def get(self, request):
        data = get_hr_summary(request)
        return Response(data)


class StaffSummaryView(APIView):
    def get(self, request):
        from_date, to_date = get_month_range_from_request(request)
        queryset = Staff.objects.filter(hire_date__lte=to_date)
        
        total_count = queryset.count()
        avg_salary = queryset.aggregate(avg_salary=Avg("salary"))["avg_salary"] or 0
        avg_age = queryset.aggregate(avg_age=Avg("age"))["avg_age"] or 0
        
        distribution = queryset.values("department__name").annotate(count=Count("id"))
        gender_split = queryset.values("gender").annotate(count=Count("id"))

        return Response({
            "total_staff": total_count,
            "avg_salary": round(avg_salary),
            "avg_age": round(avg_age),
            "distribution": distribution,
            "gender_split": gender_split,
        })
