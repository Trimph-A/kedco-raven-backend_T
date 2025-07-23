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

from datetime import date, datetime
from dateutil.relativedelta import relativedelta # type: ignore

from hr.models import Staff
from common.models import BusinessDistrict
from commercial.models import SalesRepresentative, DailyCollection, MonthlyCommercialSummary
from common.models import State


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

        def calculate_percentage_change(current, previous):
            """Calculate percentage change between current and previous values"""
            if previous == 0:
                return 100.0 if current > 0 else 0.0
            return round(((current - previous) / previous) * 100, 2)

        # Date filter based on Ribbon
        from_date, to_date = get_month_range_from_request(request)
        
        # Previous month dates for delta calculations
        prev_month_start = from_date - relativedelta(months=1)
        prev_month_end = (prev_month_start + relativedelta(months=1) - relativedelta(days=1))
        
        # Get filtering parameters
        state_filter = request.GET.get('state')  # 'all' for all states, specific state_name, or None
        district_filter = request.GET.get('district')  # 'all' for all districts, specific district_name, or None
        
        # Base queryset for staff (current month)
        current_staff_queryset = Staff.objects.filter(hire_date__lte=to_date)
        
        # Base queryset for staff (previous month)
        previous_staff_queryset = Staff.objects.filter(hire_date__lte=prev_month_end)
        
        # Apply state filtering to both querysets
        if state_filter and state_filter != 'all':
            current_staff_queryset = current_staff_queryset.filter(business_district__state__name=state_filter)
            previous_staff_queryset = previous_staff_queryset.filter(business_district__state__name=state_filter)
        
        # Apply district filtering to both querysets
        if district_filter and district_filter != 'all':
            current_staff_queryset = current_staff_queryset.filter(business_district__name=district_filter)
            previous_staff_queryset = previous_staff_queryset.filter(business_district__name=district_filter)

        # Current month metrics
        current_total_count = current_staff_queryset.count()
        current_avg_salary = current_staff_queryset.aggregate(avg_salary=Avg("salary"))["avg_salary"] or 0
        
        # Current age calculation
        current_ages = [calculate_age(staff.birth_date) for staff in current_staff_queryset if staff.birth_date]
        current_avg_age = round(sum(current_ages) / len(current_ages)) if current_ages else 0
        
        # Current retention & turnover
        current_retained_count = current_staff_queryset.filter(exit_date__isnull=True).count()
        current_exited_count = current_staff_queryset.filter(exit_date__isnull=False).count()
        current_retention_rate = (current_retained_count / current_total_count * 100) if current_total_count else 0
        current_turnover_rate = (current_exited_count / current_total_count * 100) if current_total_count else 0

        # Previous month metrics
        previous_total_count = previous_staff_queryset.count()
        previous_avg_salary = previous_staff_queryset.aggregate(avg_salary=Avg("salary"))["avg_salary"] or 0
        
        # Previous age calculation
        previous_ages = [calculate_age(staff.birth_date) for staff in previous_staff_queryset if staff.birth_date]
        previous_avg_age = round(sum(previous_ages) / len(previous_ages)) if previous_ages else 0
        
        # Previous retention & turnover
        previous_retained_count = previous_staff_queryset.filter(exit_date__isnull=True).count()
        previous_exited_count = previous_staff_queryset.filter(exit_date__isnull=False).count()
        previous_retention_rate = (previous_retained_count / previous_total_count * 100) if previous_total_count else 0
        previous_turnover_rate = (previous_exited_count / previous_total_count * 100) if previous_total_count else 0

        # Calculate deltas
        total_staff_delta = calculate_percentage_change(current_total_count, previous_total_count)
        avg_salary_delta = calculate_percentage_change(current_avg_salary, previous_avg_salary)
        avg_age_delta = calculate_percentage_change(current_avg_age, previous_avg_age)
        retention_rate_delta = calculate_percentage_change(current_retention_rate, previous_retention_rate)
        turnover_rate_delta = calculate_percentage_change(current_turnover_rate, previous_turnover_rate)

        # Distribution and gender split (using current month data)
        distribution = current_staff_queryset.values("department__name").annotate(count=Count("id"))
        gender_split = current_staff_queryset.values("gender").annotate(count=Count("id"))

        # Collections per staff calculations
        collections_data = self.calculate_collections_per_staff(
            from_date, to_date, prev_month_start, prev_month_end, state_filter, district_filter
        )

        response_data = {
            "total_staff": {
                "value": current_total_count,
                "delta": total_staff_delta
            },
            "avg_salary": {
                "value": round(current_avg_salary),
                "delta": avg_salary_delta
            },
            "avg_age": {
                "value": current_avg_age,
                "delta": avg_age_delta
            },
            "retention_rate": {
                "value": round(current_retention_rate, 2),
                "delta": retention_rate_delta
            },
            "turnover_rate": {
                "value": round(current_turnover_rate, 2),
                "delta": turnover_rate_delta
            },
            "distribution": distribution,
            "gender_split": gender_split,
            **collections_data  # Merge collections data (includes its own delta)
        }

        return Response(response_data)

    def calculate_collections_per_staff(self, from_date, to_date, prev_month_start, prev_month_end, state_filter, district_filter):
        """Calculate collections per staff for selected month and yearly trend with delta"""
        
        # Get sales reps (they are the ones who collect)
        sales_reps_queryset = SalesRepresentative.objects.all()
        
        # Apply state filtering to sales reps
        if state_filter and state_filter != 'all':
            sales_reps_queryset = sales_reps_queryset.filter(
                assigned_transformers__feeder__business_district__state__name=state_filter
            ).distinct()
        
        # Apply district filtering to sales reps
        if district_filter and district_filter != 'all':
            sales_reps_queryset = sales_reps_queryset.filter(
                assigned_transformers__feeder__business_district__name=district_filter
            ).distinct()

        # Current month collections per staff
        current_month_collections = self.get_monthly_collections_per_staff(
            from_date, to_date, sales_reps_queryset, state_filter, district_filter
        )
        
        # Previous month collections per staff for delta calculation
        previous_month_collections = self.get_monthly_collections_per_staff(
            prev_month_start, prev_month_end, sales_reps_queryset, state_filter, district_filter
        )

        # Calculate delta for collections per staff
        def calculate_collections_delta(current_data, previous_data):
            if isinstance(current_data, dict) and 'collections_per_staff' in current_data:
                current_value = current_data['collections_per_staff']
                previous_value = previous_data.get('collections_per_staff', 0) if isinstance(previous_data, dict) else 0
            else:
                current_value = current_data
                previous_value = previous_data
            
            if previous_value == 0:
                return 100.0 if current_value > 0 else 0.0
            return round(((current_value - previous_value) / previous_value) * 100, 2)

        # Add delta to current month collections
        if isinstance(current_month_collections, dict) and not any(key in current_month_collections for key in ['total_collections', 'states', 'districts']):
            # Single location case
            delta = calculate_collections_delta(current_month_collections, previous_month_collections)
            current_month_collections = {
                **current_month_collections,
                'delta': delta
            }
        elif isinstance(current_month_collections, dict):
            # Multiple locations case - add delta to each location
            updated_collections = {}
            for location, data in current_month_collections.items():
                if isinstance(data, dict) and 'collections_per_staff' in data:
                    prev_data = previous_month_collections.get(location, {})
                    delta = calculate_collections_delta(data, prev_data)
                    updated_collections[location] = {
                        **data,
                        'delta': delta
                    }
                else:
                    updated_collections[location] = data
            current_month_collections = updated_collections

        # Yearly collections per staff (all months in the selected year)
        yearly_collections = self.get_yearly_collections_per_staff(
            from_date, sales_reps_queryset, state_filter, district_filter
        )

        return {
            "collections_per_staff_current": current_month_collections,
            "collections_per_staff_yearly": yearly_collections
        }

    def get_monthly_collections_per_staff(self, from_date, to_date, sales_reps_queryset, state_filter, district_filter):
        """Get collections per staff for the selected month"""
        
        if state_filter == 'all':
            # Return data grouped by state
            states = State.objects.all()
            result = {}
            
            for state in states:
                state_sales_reps = sales_reps_queryset.filter(
                    assigned_transformers__feeder__business_district__state=state
                ).distinct()
                
                state_collections = self._calculate_monthly_collections(
                    from_date, to_date, state_sales_reps, state.name, district_filter
                )
                
                result[state.name] = {
                    "total_collections": state_collections["total"],
                    "total_sales_reps": state_collections["count"],
                    "collections_per_staff": state_collections["per_staff"]
                }
            
            return result
            
        elif district_filter == 'all':
            # Return data grouped by business district
            districts_queryset = BusinessDistrict.objects.all()
            if state_filter:
                districts_queryset = districts_queryset.filter(state__name=state_filter)
                
            result = {}
            
            for district in districts_queryset:
                district_sales_reps = sales_reps_queryset.filter(
                    assigned_transformers__feeder__business_district=district
                ).distinct()
                
                district_collections = self._calculate_monthly_collections(
                    from_date, to_date, district_sales_reps, state_filter, district.name
                )
                
                result[district.name] = {
                    "total_collections": district_collections["total"],
                    "total_sales_reps": district_collections["count"],
                    "collections_per_staff": district_collections["per_staff"]
                }
            
            return result
        
        else:
            # Single aggregated result
            collections_data = self._calculate_monthly_collections(
                from_date, to_date, sales_reps_queryset, state_filter, district_filter
            )
            
            return {
                "total_collections": collections_data["total"],
                "total_sales_reps": collections_data["count"],
                "collections_per_staff": collections_data["per_staff"]
            }

    def get_yearly_collections_per_staff(self, from_date, sales_reps_queryset, state_filter, district_filter):
        """Get collections per staff for all months in the selected year"""
        
        year = from_date.year
        monthly_data = []
        
        for month in range(1, 13):
            month_start = datetime(year, month, 1).date()
            month_end = (datetime(year, month, 1) + relativedelta(months=1) - relativedelta(days=1)).date()
            
            if state_filter == 'all':
                # Group by state for each month
                states = State.objects.all()
                month_state_data = {}
                
                for state in states:
                    state_sales_reps = sales_reps_queryset.filter(
                        assigned_transformers__feeder__business_district__state=state
                    ).distinct()
                    
                    state_collections = self._calculate_monthly_collections(
                        month_start, month_end, state_sales_reps, state.name, district_filter
                    )
                    
                    month_state_data[state.name] = state_collections["per_staff"]
                
                monthly_data.append({
                    "month": month_start.strftime("%b"),
                    "year": year,
                    "states": month_state_data
                })
                
            elif district_filter == 'all':
                # Group by district for each month
                districts_queryset = BusinessDistrict.objects.all()
                if state_filter:
                    districts_queryset = districts_queryset.filter(state__name=state_filter)
                    
                month_district_data = {}
                
                for district in districts_queryset:
                    district_sales_reps = sales_reps_queryset.filter(
                        assigned_transformers__feeder__business_district=district
                    ).distinct()
                    
                    district_collections = self._calculate_monthly_collections(
                        month_start, month_end, district_sales_reps, state_filter, district.id
                    )
                    
                    month_district_data[district.name] = district_collections["per_staff"]
                
                monthly_data.append({
                    "month": month_start.strftime("%b"),
                    "year": year,
                    "districts": month_district_data
                })
            
            else:
                # Single aggregated result for each month
                collections_data = self._calculate_monthly_collections(
                    month_start, month_end, sales_reps_queryset, state_filter, district_filter
                )
                
                monthly_data.append({
                    "month": month_start.strftime("%b"),
                    "year": year,
                    "collections_per_staff": collections_data["per_staff"]
                })
        
        return monthly_data

    def _calculate_monthly_collections(self, from_date, to_date, sales_reps_queryset, state_filter, district_filter):
        """Helper method to calculate collections for a given period and sales reps"""
        
        # Get collections from DailyCollection
        collections_queryset = DailyCollection.objects.filter(
            date__range=(from_date, to_date),
            sales_rep__in=sales_reps_queryset
        )
        
        # Apply additional filtering if needed
        if state_filter and state_filter != 'all':
            collections_queryset = collections_queryset.filter(
                distribution_transformer__feeder__business_district__state__name=state_filter
            )
        
        if district_filter and district_filter != 'all':
            collections_queryset = collections_queryset.filter(
                distribution_transformer__feeder__business_district__name=district_filter
            )
        
        total_collections = collections_queryset.aggregate(
            total=Sum('amount')
        )['total'] or 0
        
        # Also check MonthlyCommercialSummary for additional collections data
        monthly_summary_queryset = MonthlyCommercialSummary.objects.filter(
            month__range=(from_date, to_date),
            sales_rep__in=sales_reps_queryset
        )
        
        if state_filter and state_filter != 'all':
            monthly_summary_queryset = monthly_summary_queryset.filter(
                distribution_transformer__feeder__business_district__state__name=state_filter
            )
        
        if district_filter and district_filter != 'all':
            monthly_summary_queryset = monthly_summary_queryset.filter(
                distribution_transformer__feeder__business_district__name=district_filter
            )
        
        summary_collections = monthly_summary_queryset.aggregate(
            total=Sum('revenue_collected')
        )['total'] or 0
        
        # Use the higher of the two collection amounts (to avoid double counting)
        total_collections = max(total_collections, summary_collections)
        
        sales_reps_count = sales_reps_queryset.count()
        collections_per_staff = round(total_collections / sales_reps_count, 2) if sales_reps_count > 0 else 0
        
        return {
            "total": float(total_collections),
            "count": sales_reps_count,
            "per_staff": collections_per_staff
        }


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
