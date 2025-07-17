from rest_framework import viewsets, status
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
from rest_framework.decorators import action
from django.db import transaction

from common.models import BusinessDistrict as District
from .models import Staff
from .serializers import StaffSerializer




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


# class StaffViewSet(viewsets.ModelViewSet):
#     queryset = Staff.objects.all()
#     serializer_class = StaffSerializer
#     filter_backends = [DjangoFilterBackend, SearchFilter]
#     # filterset_fields = [
#     #     'department', 'role', 'state', 'district', 'gender', 'grade', 'is_active'
#     # ]
#     filterset_fields = [
#         'department', 'role', 'state', 'district', 'gender', 'grade',
#     ]
#     search_fields = ['full_name', 'email', 'phone_number']

# class StaffViewSet(viewsets.ModelViewSet):
    queryset = Staff.objects.all()
    serializer_class = StaffSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['department', 'role', 'state', 'district', 'gender', 'grade']
    search_fields = ['full_name', 'email', 'phone_number']

    def resolve_district_slug_to_uuid(self, district_slug):
        """
        Treat incoming 'district' value as the slug (e.g. 'JG-NT'),
        look it up in BusinessDistrict.slug, and return its PK.
        """
        if not district_slug:
            print("🐍 ❌ No district slug provided")
            return None

        slug = district_slug.strip()
        try:
            district = District.objects.get(slug__iexact=slug)
            return district.id
        except District.DoesNotExist:
            print(f"🐍 ❌ District slug '{slug}' not found")
            return None

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        staff_data = request.data.get('staff', [])
        print(f"🐍 Received {len(staff_data)} staff for bulk create")
        if not staff_data:
            return Response({'error': 'No staff data provided'}, status=status.HTTP_400_BAD_REQUEST)

        created, updated, errors = [], [], []
        with transaction.atomic():
            for idx, staff_item in enumerate(staff_data):
                try:
                    slug = staff_item.get('district')
                    pk = self.resolve_district_slug_to_uuid(slug)
                    if not pk:
                        errors.append({'index': idx, 'data': staff_item,
                                       'errors': f"District slug '{slug}' could not be resolved"})
                        continue
                    staff_item['district'] = pk
                    # Normalize hire_date to YYYY-MM-DD
                    if isinstance(staff_item.get('hire_date'), str) and 'T' in staff_item['hire_date']:
                        staff_item['hire_date'] = staff_item['hire_date'].split('T')[0]

                    existing = self.get_queryset().filter(
                        district=pk,
                        full_name=staff_item.get('full_name'),
                        hire_date=staff_item.get('hire_date')
                    ).first()

                    if existing:
                        serializer = self.get_serializer(existing, data=staff_item, partial=True)
                        if serializer.is_valid():
                            serializer.save()
                            updated.append(serializer.data)
                        else:
                            errors.append({'index': idx, 'data': staff_item, 'errors': serializer.errors})
                    else:
                        serializer = self.get_serializer(data=staff_item)
                        if serializer.is_valid():
                            serializer.save()
                            created.append(serializer.data)
                        else:
                            errors.append({'index': idx, 'data': staff_item, 'errors': serializer.errors})
                except Exception as e:
                    print(f"🐍 ❌ Exception at {idx}: {e}")
                    errors.append({'index': idx, 'data': staff_item, 'errors': str(e)})

        response_data = {'created': len(created), 'updated': len(updated), 'errors': len(errors),
                         'created_data': created, 'updated_data': updated}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'])
    def bulk_update(self, request):
        staff_data = request.data.get('staff', [])
        print(f"🐍 Received {len(staff_data)} staff for bulk update")
        if not staff_data:
            return Response({'error': 'No staff data provided'}, status=status.HTTP_400_BAD_REQUEST)

        updated, errors = [], []
        with transaction.atomic():
            for idx, staff_item in enumerate(staff_data):
                try:
                    comp = staff_item.get('_composite_key', {})
                    slug = comp.get('district') or staff_item.get('district')
                    pk = self.resolve_district_slug_to_uuid(slug)
                    if not pk:
                        errors.append({'index': idx, 'data': staff_item,
                                       'errors': f"District slug '{slug}' could not be resolved"})
                        continue
                    # Normalize dates
                    if comp and isinstance(comp.get('hire_date'), str) and 'T' in comp['hire_date']:
                        comp['hire_date'] = comp['hire_date'].split('T')[0]
                    if isinstance(staff_item.get('hire_date'), str) and 'T' in staff_item['hire_date']:
                        staff_item['hire_date'] = staff_item['hire_date'].split('T')[0]

                    if comp:
                        existing = self.get_queryset().filter(
                            district=pk,
                            full_name=comp.get('full_name'),
                            hire_date=comp.get('hire_date')
                        ).first()
                        data = {**staff_item, 'district': pk}
                        data.pop('_composite_key', None)
                    else:
                        existing = self.get_queryset().filter(
                            district=pk,
                            full_name=staff_item.get('full_name'),
                            hire_date=staff_item.get('hire_date')
                        ).first()
                        data = {**staff_item, 'district': pk}

                    if not existing:
                        errors.append({'index': idx, 'data': staff_item, 'errors': 'Staff not found for update'})
                        continue

                    serializer = self.get_serializer(existing, data=data, partial=True)
                    if serializer.is_valid():
                        serializer.save()
                        updated.append(serializer.data)
                    else:
                        errors.append({'index': idx, 'data': staff_item, 'errors': serializer.errors})
                except Exception as e:
                    print(f"🐍 ❌ Exception at {idx}: {e}")
                    errors.append({'index': idx, 'data': staff_item, 'errors': str(e)})

        response_data = {'updated': len(updated), 'errors': len(errors), 'updated_data': updated}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        staff_data = request.data.get('staff', [])
        print(f"🐍 Received {len(staff_data)} staff for bulk delete")
        if not staff_data:
            return Response({'error': 'No staff data provided'}, status=status.HTTP_400_BAD_REQUEST)

        deleted, errors = 0, []
        with transaction.atomic():
            for idx, staff_item in enumerate(staff_data):
                try:
                    comp = staff_item.get('_composite_key', {})
                    slug = comp.get('district') or staff_item.get('district')
                    pk = self.resolve_district_slug_to_uuid(slug)
                    if not pk:
                        errors.append({'index': idx, 'data': staff_item,
                                       'errors': f"District slug '{slug}' could not be resolved"})
                        continue
                    # Normalize dates
                    if comp and isinstance(comp.get('hire_date'), str) and 'T' in comp['hire_date']:
                        comp['hire_date'] = comp['hire_date'].split('T')[0]
                    if isinstance(staff_item.get('hire_date'), str) and 'T' in staff_item['hire_date']:
                        staff_item['hire_date'] = staff_item['hire_date'].split('T')[0]

                    if comp:
                        existing = self.get_queryset().filter(
                            district=pk,
                            full_name=comp.get('full_name'),
                            hire_date=comp.get('hire_date')
                        ).first()
                    else:
                        existing = self.get_queryset().filter(
                            district=pk,
                            full_name=staff_item.get('full_name'),
                            hire_date=staff_item.get('hire_date')
                        ).first()

                    if existing:
                        existing.delete()
                        deleted += 1
                    else:
                        errors.append({'index': idx, 'data': staff_item, 'errors': 'Staff not found for deletion'})
                except Exception as e:
                    print(f"🐍 ❌ Exception at {idx}: {e}")
                    errors.append({'index': idx, 'data': staff_item, 'errors': str(e)})

        response_data = {'deleted': deleted, 'errors': len(errors)}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)
class StaffViewSet(viewsets.ModelViewSet):
    queryset = Staff.objects.all()
    serializer_class = StaffSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['department', 'role', 'state', 'district', 'gender', 'grade']
    search_fields = ['full_name', 'email', 'phone_number']

    def resolve_district_slug_to_uuid(self, district_slug):
        """
        Treat incoming 'district' value as the slug (e.g. 'JG-NT'),
        look it up in BusinessDistrict.slug, and return its PK.
        """
        if not district_slug:
            print("🐍 ❌ No district slug provided")
            return None

        slug = district_slug.strip()
        try:
            district = District.objects.get(slug__iexact=slug)
            print(f"🐍 ✅ District slug '{slug}' resolved to PK: {district.id}")  # NEW DEBUG
            return district.id
        except District.DoesNotExist:
            print(f"🐍 ❌ District slug '{slug}' not found")
            return None

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        staff_data = request.data.get('staff', [])
        print(f"🐍 Received {len(staff_data)} staff for bulk create")
        if not staff_data:
            return Response({'error': 'No staff data provided'}, status=status.HTTP_400_BAD_REQUEST)

        created, updated, errors = [], [], []
        with transaction.atomic():
            for idx, staff_item in enumerate(staff_data):
                try:
                    print(f"🐍 📝 Processing item {idx}: {staff_item}")  # NEW DEBUG
                    
                    slug = staff_item.get('district')
                    pk = self.resolve_district_slug_to_uuid(slug)
                    if not pk:
                        errors.append({'index': idx, 'data': staff_item,
                                       'errors': f"District slug '{slug}' could not be resolved"})
                        continue
                    staff_item['district'] = pk
                    
                    # Normalize hire_date to YYYY-MM-DD
                    original_hire_date = staff_item.get('hire_date')  # NEW DEBUG
                    if isinstance(staff_item.get('hire_date'), str) and 'T' in staff_item['hire_date']:
                        staff_item['hire_date'] = staff_item['hire_date'].split('T')[0]
                    print(f"🐍 📅 Hire date normalized: {original_hire_date} → {staff_item.get('hire_date')}")  # NEW DEBUG

                    # NEW DEBUG: Check what we're searching for
                    search_criteria = {
                        'district': pk,
                        'full_name': staff_item.get('full_name'),
                        'hire_date': staff_item.get('hire_date')
                    }
                    print(f"🐍 🔍 Looking for existing staff with: {search_criteria}")
                    
                    existing = self.get_queryset().filter(**search_criteria).first()
                    print(f"🐍 📊 Found existing record: {existing}")  # NEW DEBUG
                    
                    if existing:
                        print(f"🐍 🔄 UPDATING existing staff ID: {existing.id}")  # NEW DEBUG
                        serializer = self.get_serializer(existing, data=staff_item, partial=True)
                        if serializer.is_valid():
                            saved_instance = serializer.save()
                            print(f"🐍 ✅ Successfully updated staff ID: {saved_instance.id}")  # NEW DEBUG
                            updated.append(serializer.data)
                        else:
                            print(f"🐍 ❌ Update validation failed: {serializer.errors}")  # NEW DEBUG
                            errors.append({'index': idx, 'data': staff_item, 'errors': serializer.errors})
                    else:
                        print(f"🐍 ➕ CREATING new staff record")  # NEW DEBUG
                        serializer = self.get_serializer(data=staff_item)
                        if serializer.is_valid():
                            saved_instance = serializer.save()
                            print(f"🐍 ✅ Successfully created staff ID: {saved_instance.id}")  # NEW DEBUG
                            created.append(serializer.data)
                        else:
                            print(f"🐍 ❌ Create validation failed: {serializer.errors}")  # NEW DEBUG
                            errors.append({'index': idx, 'data': staff_item, 'errors': serializer.errors})
                except Exception as e:
                    print(f"🐍 ❌ Exception at {idx}: {e}")
                    import traceback
                    print(f"🐍 📋 Full traceback: {traceback.format_exc()}")  # NEW DEBUG
                    errors.append({'index': idx, 'data': staff_item, 'errors': str(e)})

        print(f"🐍 📈 Final results: Created={len(created)}, Updated={len(updated)}, Errors={len(errors)}")  # NEW DEBUG
        response_data = {'created': len(created), 'updated': len(updated), 'errors': len(errors),
                         'created_data': created, 'updated_data': updated}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'])
    def bulk_update(self, request):
        staff_data = request.data.get('staff', [])
        print(f"🐍 Received {len(staff_data)} staff for bulk update")
        if not staff_data:
            return Response({'error': 'No staff data provided'}, status=status.HTTP_400_BAD_REQUEST)

        updated, errors = [], []
        with transaction.atomic():
            for idx, staff_item in enumerate(staff_data):
                try:
                    print(f"🐍 📝 Processing UPDATE item {idx}: {staff_item}")  # NEW DEBUG
                    
                    comp = staff_item.get('_composite_key', {})
                    slug = comp.get('district') or staff_item.get('district')
                    pk = self.resolve_district_slug_to_uuid(slug)
                    if not pk:
                        errors.append({'index': idx, 'data': staff_item,
                                       'errors': f"District slug '{slug}' could not be resolved"})
                        continue
                        
                    # Normalize dates
                    if comp and isinstance(comp.get('hire_date'), str) and 'T' in comp['hire_date']:
                        comp['hire_date'] = comp['hire_date'].split('T')[0]
                    if isinstance(staff_item.get('hire_date'), str) and 'T' in staff_item['hire_date']:
                        staff_item['hire_date'] = staff_item['hire_date'].split('T')[0]

                    if comp:
                        search_criteria = {
                            'district': pk,
                            'full_name': comp.get('full_name'),
                            'hire_date': comp.get('hire_date')
                        }
                        print(f"🐍 🔍 UPDATE: Looking for existing staff with composite key: {search_criteria}")  # NEW DEBUG
                        existing = self.get_queryset().filter(**search_criteria).first()
                        data = {**staff_item, 'district': pk}
                        data.pop('_composite_key', None)
                    else:
                        search_criteria = {
                            'district': pk,
                            'full_name': staff_item.get('full_name'),
                            'hire_date': staff_item.get('hire_date')
                        }
                        print(f"🐍 🔍 UPDATE: Looking for existing staff with direct fields: {search_criteria}")  # NEW DEBUG
                        existing = self.get_queryset().filter(**search_criteria).first()
                        data = {**staff_item, 'district': pk}

                    print(f"🐍 📊 UPDATE: Found existing record: {existing}")  # NEW DEBUG

                    if not existing:
                        print(f"🐍 ❌ UPDATE: Staff not found for update")  # NEW DEBUG
                        errors.append({'index': idx, 'data': staff_item, 'errors': 'Staff not found for update'})
                        continue

                    serializer = self.get_serializer(existing, data=data, partial=True)
                    if serializer.is_valid():
                        saved_instance = serializer.save()
                        print(f"🐍 ✅ UPDATE: Successfully updated staff ID: {saved_instance.id}")  # NEW DEBUG
                        updated.append(serializer.data)
                    else:
                        print(f"🐍 ❌ UPDATE: Validation failed: {serializer.errors}")  # NEW DEBUG
                        errors.append({'index': idx, 'data': staff_item, 'errors': serializer.errors})
                except Exception as e:
                    print(f"🐍 ❌ UPDATE Exception at {idx}: {e}")
                    import traceback
                    print(f"🐍 📋 UPDATE Full traceback: {traceback.format_exc()}")  # NEW DEBUG
                    errors.append({'index': idx, 'data': staff_item, 'errors': str(e)})

        print(f"🐍 📈 UPDATE Final results: Updated={len(updated)}, Errors={len(errors)}")  # NEW DEBUG
        response_data = {'updated': len(updated), 'errors': len(errors), 'updated_data': updated}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        staff_data = request.data.get('staff', [])
        print(f"🐍 Received {len(staff_data)} staff for bulk delete")
        if not staff_data:
            return Response({'error': 'No staff data provided'}, status=status.HTTP_400_BAD_REQUEST)

        deleted, errors = 0, []
        with transaction.atomic():
            for idx, staff_item in enumerate(staff_data):
                try:
                    print(f"🐍 📝 Processing DELETE item {idx}: {staff_item}")  # NEW DEBUG
                    
                    comp = staff_item.get('_composite_key', {})
                    slug = comp.get('district') or staff_item.get('district')
                    pk = self.resolve_district_slug_to_uuid(slug)
                    if not pk:
                        errors.append({'index': idx, 'data': staff_item,
                                       'errors': f"District slug '{slug}' could not be resolved"})
                        continue
                        
                    # Normalize dates
                    if comp and isinstance(comp.get('hire_date'), str) and 'T' in comp['hire_date']:
                        comp['hire_date'] = comp['hire_date'].split('T')[0]
                    if isinstance(staff_item.get('hire_date'), str) and 'T' in staff_item['hire_date']:
                        staff_item['hire_date'] = staff_item['hire_date'].split('T')[0]

                    if comp:
                        search_criteria = {
                            'district': pk,
                            'full_name': comp.get('full_name'),
                            'hire_date': comp.get('hire_date')
                        }
                        print(f"🐍 🔍 DELETE: Looking for existing staff with composite key: {search_criteria}")  # NEW DEBUG
                        existing = self.get_queryset().filter(**search_criteria).first()
                    else:
                        search_criteria = {
                            'district': pk,
                            'full_name': staff_item.get('full_name'),
                            'hire_date': staff_item.get('hire_date')
                        }
                        print(f"🐍 🔍 DELETE: Looking for existing staff with direct fields: {search_criteria}")  # NEW DEBUG
                        existing = self.get_queryset().filter(**search_criteria).first()

                    print(f"🐍 📊 DELETE: Found existing record: {existing}")  # NEW DEBUG

                    if existing:
                        existing.delete()
                        print(f"🐍 ✅ DELETE: Successfully deleted staff")  # NEW DEBUG
                        deleted += 1
                    else:
                        print(f"🐍 ❌ DELETE: Staff not found for deletion")  # NEW DEBUG
                        errors.append({'index': idx, 'data': staff_item, 'errors': 'Staff not found for deletion'})
                except Exception as e:
                    print(f"🐍 ❌ DELETE Exception at {idx}: {e}")
                    import traceback
                    print(f"🐍 📋 DELETE Full traceback: {traceback.format_exc()}")  # NEW DEBUG
                    errors.append({'index': idx, 'data': staff_item, 'errors': str(e)})

        print(f"🐍 📈 DELETE Final results: Deleted={deleted}, Errors={len(errors)}")  # NEW DEBUG
        response_data = {'deleted': deleted, 'errors': len(errors)}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)


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
