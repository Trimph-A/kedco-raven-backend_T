from rest_framework import viewsets
from .models import *
from .serializers import *
from commercial.utils import get_filtered_feeders
from commercial.date_filters import get_date_range_from_request
from financial.metrics import (
    get_total_cost,
    get_total_revenue_billed,
    get_opex_breakdown,
    get_tariff_loss,
)
from commercial.metrics import get_total_collections
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from common.mixins import DistrictLocationFilterMixin
from common.models import State, BusinessDistrict

from django.db.models import Sum
from django.utils.timezone import now
from rest_framework.decorators import api_view
from rest_framework.response import Response
from datetime import date
from dateutil.relativedelta import relativedelta # type: ignore
from commercial.models import MonthlyCommercialSummary, DailyRevenueCollected, DailyEnergyDelivered
from django.db.models import Q
from .metrics import get_financial_feeder_data
from commercial.models import SalesRepresentative
from django.db.models import Count
from datetime import datetime, timedelta
from rest_framework import status
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from django.db import transaction
from commercial.serializers import SalesRepresentativeSerializer
from common.models import BusinessDistrict as District



class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer


# class ExpenseViewSet(DistrictLocationFilterMixin, viewsets.ModelViewSet):
#     # queryset = Expense.objects.all()
#     serializer_class = ExpenseSerializer
#     filter_backends = [DjangoFilterBackend]
#     filterset_fields = {'district', 'gl_breakdown', 'opex_category', 'date'}

#     def get_queryset(self):
#         qs = Expense.objects.all()
#         return self.filter_by_location(qs)

class OpexViewSet(DistrictLocationFilterMixin, viewsets.ModelViewSet):
    # queryset = Expense.objects.all()
    serializer_class = OpexSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {'district', 'gl_breakdown', 'opex_category', 'date'}

    def get_queryset(self):
        qs = Opex.objects.all()
        return self.filter_by_location(qs)

    def get_object(self):
        """
        Override to handle composite key lookups for UPDATE/DELETE operations
        """
        queryset = self.get_queryset()
        
        # Check if this is a composite key lookup (from sync operations)
        if hasattr(self.request, 'data') and '_composite_key' in self.request.data:
            composite_key = self.request.data['_composite_key']
            return get_object_or_404(
                queryset,
                district=composite_key['district'],
                date=composite_key['date'],
                purpose=composite_key['purpose']
            )
        
        # For URL-based lookups (traditional REST), try to use pk
        if 'pk' in self.kwargs:
            return get_object_or_404(queryset, pk=self.kwargs['pk'])
        
        # Fallback to first object (shouldn't happen in normal operations)
        return queryset.first()

    def create(self, request, *args, **kwargs):
        """
        Handle INSERT operations with upsert logic for sync
        """
        data = request.data
        
        # Check if record already exists (upsert logic)
        existing = self.get_queryset().filter(
            district=data.get('district'),
            date=data.get('date'),
            purpose=data.get('purpose')
        ).first()
        
        if existing:
            # Update existing record
            serializer = self.get_serializer(existing, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            # Create new record
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """
        Handle UPDATE operations using composite key
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # Remove composite key from data before serialization
        data = request.data.copy()
        if '_composite_key' in data:
            del data['_composite_key']
        
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """
        Handle DELETE operations using composite key
        """
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def list(self, request, *args, **kwargs):
        """
        Enhanced list view with better filtering for sync operations
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        # Add support for composite key filtering in list operations
        district = request.query_params.get('district')
        date = request.query_params.get('date')
        purpose = request.query_params.get('purpose')
        
        if district and date and purpose:
            queryset = queryset.filter(
                district=district,
                date=date,
                purpose=purpose
            )
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """
        Handle bulk INSERT operations for sync (like Excel uploads)
        Expected payload: {"expenses": [expense1, expense2, ...]}
        """
        expenses_data = request.data.get('expenses', [])
        print(f"🐍 Received {len(expenses_data)} expenses for bulk create")

        if not expenses_data:
            return Response(
                {'error': 'No expenses data provided'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        created_expenses = []
        updated_expenses = []
        errors = []

        with transaction.atomic():
            for idx, expense_data in enumerate(expenses_data):
                try:
                    print(f"🐍 Processing expense {idx}: {expense_data}")
                    
                    # 🆕 RESOLVE DISTRICT CODE TO UUID
                    district_code = expense_data.get('district')
                    try:
                        # Assuming your District model has a 'code' field
                        district_obj = District.objects.get(code=district_code)
                        expense_data['district'] = district_obj.id  # Use UUID
                        print(f"🐍 ✅ Resolved district '{district_code}' to UUID: {district_obj.id}")
                    except District.DoesNotExist:
                        print(f"🐍 ❌ District not found: {district_code}")
                        errors.append({
                            'index': idx,
                            'data': expense_data,
                            'errors': f'District code "{district_code}" not found'
                        })
                        continue
                    
                    # Check if record exists (upsert logic) - now using UUID
                    existing = self.get_queryset().filter(
                        district=expense_data.get('district'),  # Now UUID
                        date=expense_data.get('date'),
                        purpose=expense_data.get('purpose')
                    ).first()

                    if existing:
                        print(f"🐍 Found existing record, updating...")
                        serializer = self.get_serializer(existing, data=expense_data, partial=True)
                        if serializer.is_valid():
                            instance = serializer.save()
                            print(f"🐍 ✅ Updated record with ID: {instance.id}")
                            print(f"🐍 ✅ Updated data: {serializer.data}")
                            updated_expenses.append(serializer.data)
                        else:
                            print(f"🐍 ❌ Update validation failed: {serializer.errors}")
                            errors.append({
                                'index': idx,
                                'data': expense_data,
                                'errors': serializer.errors
                            })
                    else:
                        print(f"🐍 Creating new record...")
                        serializer = self.get_serializer(data=expense_data)
                        if serializer.is_valid():
                            instance = serializer.save()
                            print(f"🐍 ✅ Created record with ID: {instance.id}")
                            print(f"🐍 ✅ Created data: {serializer.data}")
                            created_expenses.append(serializer.data)
                        else:
                            print(f"🐍 ❌ Create validation failed: {serializer.errors}")
                            errors.append({
                                'index': idx,
                                'data': expense_data,
                                'errors': serializer.errors
                            })

                except Exception as e:
                    print(f"🐍 ❌ Exception processing expense {idx}: {str(e)}")
                    import traceback
                    print(f"🐍 ❌ Full traceback: {traceback.format_exc()}")
                    errors.append({
                        'index': idx,
                        'data': expense_data,
                        'errors': str(e)
                    })

        print(f"🐍 Final summary: Created {len(created_expenses)}, Updated {len(updated_expenses)}, Errors {len(errors)}")
        
        response_data = {
            'created': len(created_expenses),
            'updated': len(updated_expenses),
            'errors': len(errors),
            'created_data': created_expenses,
            'updated_data': updated_expenses
        }

        if errors:
            response_data['error_details'] = errors
            print(f"🐍 ❌ Error details: {errors}")

        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'])
    def bulk_update(self, request):
        """
        Handle bulk UPDATE operations for sync
        Expected payload: {"expenses": [expense1, expense2, ...]}
        """
        expenses_data = request.data.get('expenses', [])
        print(f"🐍 Received {len(expenses_data)} expenses for bulk update")
        
        if not expenses_data:
            return Response(
                {'error': 'No expenses data provided'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        updated_expenses = []
        errors = []

        with transaction.atomic():
            for idx, expense_data in enumerate(expenses_data):
                try:
                    print(f"🐍 Processing update expense {idx}: {expense_data}")
                    
                    # 🆕 RESOLVE DISTRICT CODE TO UUID
                    district_code = None
                    if '_composite_key' in expense_data:
                        district_code = expense_data['_composite_key'].get('district')
                    else:
                        district_code = expense_data.get('district')
                    
                    try:
                        district_obj = District.objects.get(code=district_code)
                        district_uuid = district_obj.id
                        print(f"🐍 ✅ Resolved district '{district_code}' to UUID: {district_uuid}")
                    except District.DoesNotExist:
                        print(f"🐍 ❌ District not found: {district_code}")
                        errors.append({
                            'index': idx,
                            'data': expense_data,
                            'errors': f'District code "{district_code}" not found'
                        })
                        continue
                    
                    # Find existing record using UUID
                    if '_composite_key' in expense_data:
                        composite_key = expense_data['_composite_key']
                        existing = self.get_queryset().filter(
                            district=district_uuid,  # Use UUID
                            date=composite_key['date'],
                            purpose=composite_key['purpose']
                        ).first()
                    else:
                        existing = self.get_queryset().filter(
                            district=district_uuid,  # Use UUID
                            date=expense_data.get('date'),
                            purpose=expense_data.get('purpose')
                        ).first()

                    if existing:
                        # Remove composite key from data and update district with UUID
                        clean_data = expense_data.copy()
                        if '_composite_key' in clean_data:
                            del clean_data['_composite_key']
                        clean_data['district'] = district_uuid  # Set UUID
                        
                        print(f"🐍 Found existing record for update, ID: {existing.id}")
                        serializer = self.get_serializer(existing, data=clean_data, partial=True)
                        if serializer.is_valid():
                            instance = serializer.save()
                            print(f"🐍 ✅ Updated record with ID: {instance.id}")
                            print(f"🐍 ✅ Updated data: {serializer.data}")
                            updated_expenses.append(serializer.data)
                        else:
                            print(f"🐍 ❌ Update validation failed: {serializer.errors}")
                            errors.append({
                                'index': idx,
                                'data': expense_data,
                                'errors': serializer.errors
                            })
                    else:
                        print(f"🐍 ❌ Record not found for update")
                        errors.append({
                            'index': idx,
                            'data': expense_data,
                            'errors': 'Record not found for update'
                        })

                except Exception as e:
                    print(f"🐍 ❌ Exception processing update expense {idx}: {str(e)}")
                    import traceback
                    print(f"🐍 ❌ Full traceback: {traceback.format_exc()}")
                    errors.append({
                        'index': idx,
                        'data': expense_data,
                        'errors': str(e)
                    })

        print(f"🐍 Update summary: Updated {len(updated_expenses)}, Errors {len(errors)}")
        
        response_data = {
            'updated': len(updated_expenses),
            'errors': len(errors),
            'updated_data': updated_expenses
        }

        if errors:
            response_data['error_details'] = errors
            print(f"🐍 ❌ Update error details: {errors}")

        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        """
        Handle bulk DELETE operations for sync
        Expected payload: {"expenses": [expense1, expense2, ...]}
        """
        expenses_data = request.data.get('expenses', [])
        print(f"🐍 Received {len(expenses_data)} expenses for bulk delete")
        
        if not expenses_data:
            return Response(
                {'error': 'No expenses data provided'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        deleted_count = 0
        errors = []

        with transaction.atomic():
            for idx, expense_data in enumerate(expenses_data):
                try:
                    print(f"🐍 Processing delete expense {idx}: {expense_data}")
                    
                    # 🆕 RESOLVE DISTRICT CODE TO UUID
                    district_code = None
                    if '_composite_key' in expense_data:
                        district_code = expense_data['_composite_key'].get('district')
                    else:
                        district_code = expense_data.get('district')
                    
                    try:
                        district_obj = District.objects.get(code=district_code)
                        district_uuid = district_obj.id
                        print(f"🐍 ✅ Resolved district '{district_code}' to UUID: {district_uuid}")
                    except District.DoesNotExist:
                        print(f"🐍 ❌ District not found: {district_code}")
                        errors.append({
                            'index': idx,
                            'data': expense_data,
                            'errors': f'District code "{district_code}" not found'
                        })
                        continue
                    
                    # Find existing record using UUID
                    if '_composite_key' in expense_data:
                        composite_key = expense_data['_composite_key']
                        existing = self.get_queryset().filter(
                            district=district_uuid,  # Use UUID
                            date=composite_key['date'],
                            purpose=composite_key['purpose']
                        ).first()
                    else:
                        existing = self.get_queryset().filter(
                            district=district_uuid,  # Use UUID
                            date=expense_data.get('date'),
                            purpose=expense_data.get('purpose')
                        ).first()

                    if existing:
                        record_id = existing.id
                        existing.delete()
                        deleted_count += 1
                        print(f"🐍 ✅ Deleted record with ID: {record_id}")
                    else:
                        print(f"🐍 ❌ Record not found for deletion")
                        errors.append({
                            'index': idx,
                            'data': expense_data,
                            'errors': 'Record not found for deletion'
                        })

                except Exception as e:
                    print(f"🐍 ❌ Exception processing delete expense {idx}: {str(e)}")
                    import traceback
                    print(f"🐍 ❌ Full traceback: {traceback.format_exc()}")
                    errors.append({
                        'index': idx,
                        'data': expense_data,
                        'errors': str(e)
                    })

        print(f"🐍 Delete summary: Deleted {deleted_count}, Errors {len(errors)}")
        
        response_data = {
            'deleted': deleted_count,
            'errors': len(errors)
        }

        if errors:
            response_data['error_details'] = errors
            print(f"🐍 ❌ Delete error details: {errors}")

        return Response(response_data, status=status.HTTP_200_OK)


class GLBreakdownViewSet(viewsets.ModelViewSet):
    queryset = GLBreakdown.objects.all()
    serializer_class = GLBreakdownSerializer


class MonthlyRevenueBilledViewSet(viewsets.ModelViewSet):
    serializer_class = MonthlyRevenueBilledSerializer

    def get_queryset(self):
        feeders = get_filtered_feeders(self.request)
        month_from, month_to = get_date_range_from_request(self.request, 'month')

        qs = MonthlyRevenueBilled.objects.filter(feeder__in=feeders)

        if month_from and month_to:
            qs = qs.filter(month__range=(month_from, month_to))
        elif month_from:
            qs = qs.filter(month__gte=month_from)
        elif month_to:
            qs = qs.filter(month__lte=month_to)

        return qs
    
class SalaryPaymentViewSet(viewsets.ModelViewSet):
    queryset = SalaryPayment.objects.all()
    serializer_class = SalaryPaymentSerializer
    filterset_fields = ["district", "month", "staff"]


class FinancialSummaryView(APIView):
    def get(self, request):
        data = {
            "total_cost": round(get_total_cost(request), 2),
            "total_revenue_billed": round(get_total_revenue_billed(request), 2),
            "total_collections": round(get_total_collections(request), 2),
            "opex_breakdown": get_opex_breakdown(request),
            "tariff_loss_percentage": get_tariff_loss(request),
        }
        return Response(data)
    






@api_view(["GET"])
def financial_overview_view(request):
    year = int(request.query_params.get("year", date.today().year))
    month = request.query_params.get("month")
    state_name = request.query_params.get("state")
    district_name = request.query_params.get("business_district")

    # Filters
    commercial_filter = Q(month__year=year)
    expense_filter = Q(date__year=year)

    if district_name:
        commercial_filter &= Q(sales_rep__assigned_feeders__business_district__name__iexact=district_name)
        expense_filter &= Q(district__name__iexact=district_name)
    elif state_name:
        commercial_filter &= Q(sales_rep__assigned_feeders__business_district__state__name__iexact=state_name)
        expense_filter &= Q(district__state__name__iexact=state_name)

    # --- Monthly Commercial Collections (Always full year) ---
    monthly_collections = MonthlyCommercialSummary.objects.filter(commercial_filter).values_list("month__month").annotate(
        total_collections=Sum("revenue_collected"),
        total_billed=Sum("revenue_billed")
    )

    monthly_data = {m: {"collections": 0, "billed": 0} for m in range(1, 13)}
    for m, collected, billed in monthly_collections:
        monthly_data[m]["collections"] = float(collected or 0)
        monthly_data[m]["billed"] = float(billed or 0)

    monthly_summaries = [
        {
            "month": date(year, m, 1).strftime("%b"),
            "collections": monthly_data[m]["collections"],
            "billed": monthly_data[m]["billed"],
        }
        for m in range(1, 13)
    ]

    # --- Revenue/Collection and Expenses (Filtered by month if provided) ---
    if month:
        try:
            month = int(month)
            start_month = date(year, month, 1)
            end_month = start_month + relativedelta(months=1)

            monthly_filter = Q(month__gte=start_month, month__lt=end_month)
            expense_month_filter = Q(date__gte=start_month, date__lt=end_month)

            current_month_filter = commercial_filter & monthly_filter
            expense_filter &= expense_month_filter
        except ValueError:
            return Response({"error": "Invalid month format"}, status=400)
    else:
        current_month_filter = commercial_filter  # use whole year

    # Revenue/Collection for the month/year
    monthly_summary = MonthlyCommercialSummary.objects.filter(current_month_filter).aggregate(
        revenue_billed=Sum("revenue_billed"),
        revenue_collected=Sum("revenue_collected")
    )

    revenue_billed = float(monthly_summary["revenue_billed"] or 0)
    revenue_collected = float(monthly_summary["revenue_collected"] or 0)

    # Expenses for selected scope
    expenses = Opex.objects.filter(expense_filter)
    total_cost = float(expenses.aggregate(total=Sum("credit"))["total"] or 0)

    opex_breakdown = (
        expenses.values("opex_category__name")
        .annotate(total=Sum("credit"))
        .order_by("opex_category__name")
    )

    breakdown = [
        {
            "category": entry["opex_category__name"] or "Uncategorized",
            "amount": float(entry["total"] or 0)
        }
        for entry in opex_breakdown
    ]


    # --- Historical Financial Breakdown (last 5 months including selected) ---
    selected_month = int(request.query_params.get("month", date.today().month))
    selected_date = date(year, selected_month, 1)
    prev_months = [selected_date - relativedelta(months=i) for i in range(4, -1, -1)]

    historical_data = []

    for dt in prev_months:
        month_start = date(dt.year, dt.month, 1)
        month_end = month_start + relativedelta(months=1)

        # MonthlyCommercialSummary filters by month field
        summary_filter = commercial_filter & Q(month__gte=month_start, month__lt=month_end)

        # Expense filters by date field
        cost_filter = expense_filter & Q(date__gte=month_start, date__lt=month_end)

        summary = MonthlyCommercialSummary.objects.filter(summary_filter).aggregate(
            revenue_collected=Sum("revenue_collected"),
            revenue_billed=Sum("revenue_billed")
        )
        cost = Opex.objects.filter(cost_filter).aggregate(total=Sum("credit"))["total"] or 0

        historical_data.append({
            "month": dt.strftime("%b"),
            "total_cost": float(cost),
            "revenue_billed": float(summary["revenue_billed"] or 0),
            "revenue_collected": float(summary["revenue_collected"] or 0),
        })

    # Add deltas (percentage change from previous month)
    for i in range(1, len(historical_data)):
        for key in ["total_cost", "revenue_billed", "revenue_collected"]:
            prev = historical_data[i - 1][key]
            curr = historical_data[i][key]
            delta = ((curr - prev) / prev * 100) if prev else 0
            historical_data[i][f"{key}_delta"] = round(delta, 2)



    return Response({
        "monthly_summary": monthly_summaries,
        "revenue_billed": revenue_billed,
        "revenue_collected": revenue_collected,
        "total_cost": total_cost,
        "opex_breakdown": breakdown,
        "historical_summary": historical_data,
    })

@api_view(['GET'])
def financial_feeder_view(request):
    """
    Returns feeder-level financial metrics filtered by state or business district and date.
    Business district filter takes precedence.
    """
    data = get_financial_feeder_data(request)
    return Response(data)


@api_view(["GET"])
def sales_rep_performance_view(request, rep_id):
    try:
        rep = SalesRepresentative.objects.get(id=rep_id)
    except SalesRepresentative.DoesNotExist:
        return Response({"error": "Sales rep not found."}, status=status.HTTP_404_NOT_FOUND)

    mode = request.GET.get("mode", "monthly")
    year = int(request.GET.get("year", datetime.now().year))
    month = int(request.GET.get("month", datetime.now().month))

    start_date = datetime(year, month, 1)
    end_date = (start_date + relativedelta(months=1)) - timedelta(days=1)

    # Current month summary
    current_summary = MonthlyCommercialSummary.objects.filter(
        sales_rep=rep,
        month__range=(start_date, end_date)
    ).aggregate(
        revenue_billed=Sum("revenue_billed"),
        revenue_collected=Sum("revenue_collected"),
    )

    revenue_billed = current_summary["revenue_billed"] or 0
    revenue_collected = current_summary["revenue_collected"] or 0
    outstanding_billed = revenue_billed - revenue_collected

    # All-time
    all_time_summary = MonthlyCommercialSummary.objects.filter(sales_rep=rep).aggregate(
        all_time_billed=Sum("revenue_billed"),
        all_time_collected=Sum("revenue_collected")
    )
    outstanding_all_time = (all_time_summary["all_time_billed"] or 0) - (all_time_summary["all_time_collected"] or 0)

    # ---- Previous 4 Months ---- #
    monthly_summaries = []
    for i in range(4):
        ref_date = start_date - relativedelta(months=i)
        month_start = ref_date.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - timedelta(days=1)

        summary = MonthlyCommercialSummary.objects.filter(
            sales_rep=rep,
            month__range=(month_start, month_end)
        ).aggregate(
            revenue_billed=Sum("revenue_billed") or 0,
            revenue_collected=Sum("revenue_collected") or 0,
        )

        billed = summary["revenue_billed"] or 0
        collected = summary["revenue_collected"] or 0
        outstanding = billed - collected

        monthly_summaries.append({
            "month": month_start.strftime("%b"),
            "revenue_billed": billed,
            "revenue_collected": collected,
            "outstanding_billed": outstanding
        })

    monthly_summaries.reverse()

    return Response({
        "sales_rep": {
            "id": str(rep.id),
            "name": rep.name
        },
        "current": {
            "revenue_billed": revenue_billed,
            "revenue_collected": revenue_collected,
            "outstanding_billed": outstanding_billed
        },
        "outstanding_all_time": outstanding_all_time,
        "previous_months": monthly_summaries
    })

@api_view(["GET"])
def list_sales_reps(request):
    reps = SalesRepresentative.objects.all()[:10]
    data = SalesRepresentativeSerializer(reps, many=True).data
    return Response(data)


@api_view(["GET"])
def sales_rep_global_summary_view(request):
    mode = request.GET.get("mode", "monthly")

    if mode == "monthly":
        try:
            year = int(request.GET.get("year", datetime.now().year))
            month = int(request.GET.get("month", datetime.now().month))
            start_date = datetime(year, month, 1)
            end_date = (start_date + relativedelta(months=1)) - relativedelta(days=1)
        except (TypeError, ValueError):
            return Response({"error": "Invalid year or month for monthly mode"}, status=400)
    else:
        from common.filters import get_date_range_from_request
        start_date, end_date = get_date_range_from_request(request, "month")

    summary = MonthlyCommercialSummary.objects.filter(
        month__range=(start_date, end_date)
    ).aggregate(
        total_billed=Sum("revenue_billed"),
        total_collected=Sum("revenue_collected"),
        active_accounts=Count("id")
    )

    total_billed = summary["total_billed"] or 0
    total_collected = summary["total_collected"] or 0
    active_accounts = summary["active_accounts"] or 0

    return Response({
        "daily_run_rate": total_billed / 30,
        "collections_on_outstanding": total_collected,
        "active_accounts": active_accounts,
        "suspended_accounts": 0
    })


import random
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import date
from django.db.models import Sum
from decimal import Decimal

from financial.models import Opex
from commercial.models import MonthlyCommercialSummary
from common.models import State, BusinessDistrict
from common.models import BusinessDistrict as District

class FinancialAllStatesView(APIView):
    def get(self, request):
        year = int(request.GET.get("year"))
        month = int(request.GET.get("month"))
        target_month = date(year, month, 1)

        results = []

        for state in State.objects.all():
            # --- Total Cost (from Expenses) ---
            expense_total = Opex.objects.filter(
                date__year=year,
                date__month=month,
                district__state=state
            ).aggregate(total_cost=Sum("credit"))["total_cost"] or Decimal("0")

            # --- Revenue Billed and Collections (from MonthlyCommercialSummary) ---
            sales_reps = SalesRepresentative.objects.filter(
                assigned_transformers__feeder__business_district__state=state
            ).distinct()

            commercial_data = MonthlyCommercialSummary.objects.filter(
                month=target_month,
                sales_rep__in=sales_reps
            ).aggregate(
                revenue_billed=Sum("revenue_billed"),
                collections=Sum("revenue_collected")
            )

            revenue_billed = commercial_data["revenue_billed"] or Decimal("0")
            collections = commercial_data["collections"] or Decimal("0")

            # --- Random Tariff Data ---
            myto_tariff = Decimal(random.choice([59, 60, 61]))
            actual_tariff = Decimal(random.choice([70, 72, 68]))
            tariff_loss = myto_tariff - actual_tariff

            # --- Compile State Metrics ---
            results.append({
                "state": state.name,
                "total_cost": round(expense_total, 2),
                "revenue_billed": round(revenue_billed, 2),
                "collections": round(collections, 2),
                "myto_allowed_tariff": f"{myto_tariff}",
                "actual_tariff_collected": f"{actual_tariff}",
                "tariff_loss": f"{tariff_loss}"
            })

        return Response(results, status=status.HTTP_200_OK)



import random
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import date
from django.db.models import Sum
from decimal import Decimal

from financial.models import Opex
from commercial.models import MonthlyCommercialSummary
from common.models import BusinessDistrict

class FinancialAllBusinessDistrictsView(APIView):
    def get(self, request):
        year = int(request.GET.get("year"))
        month = int(request.GET.get("month"))
        state_name = request.GET.get("state")

        if not state_name:
            return Response({"error": "state is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            state = State.objects.get(name__iexact=state_name)
        except State.DoesNotExist:
            return Response({"error": "State not found"}, status=status.HTTP_404_NOT_FOUND)

        target_month = date(year, month, 1)
        results = []

        districts = BusinessDistrict.objects.filter(state=state)

        for district in districts:
            # Total Cost (Expense model)
            cost = Opex.objects.filter(
                district=district,
                date__year=year,
                date__month=month
            ).aggregate(total_cost=Sum("credit"))["total_cost"] or Decimal("0")

            # Get all sales reps mapped to district via feeder
            sales_reps = SalesRepresentative.objects.filter(
                assigned_transformers__feeder__business_district=district
            ).distinct()

            commercial_data = MonthlyCommercialSummary.objects.filter(
                month=target_month,
                sales_rep__in=sales_reps
            ).aggregate(
                revenue_billed=Sum("revenue_billed"),
                collections=Sum("revenue_collected")
            )

            billed = commercial_data["revenue_billed"] or Decimal("0")
            collected = commercial_data["collections"] or Decimal("0")

            # Random Tariff Loss (simulate)
            tariff_loss = Decimal(random.randint(10, 50))

            results.append({
                "district": district.name,
                "total_cost": round(cost, 2),
                "revenue_billed": round(billed, 2),
                "collections": round(collected, 2),
                "tariff_loss": f"{tariff_loss}"
            })

        return Response(results, status=status.HTTP_200_OK)



from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import date
from django.db.models import Sum
from decimal import Decimal
from random import randint

from common.models import Band, Feeder
from commercial.models import MonthlyCommercialSummary, SalesRepresentative
from financial.models import Opex
from technical.models import EnergyDelivered


class FinancialServiceBandMetricsView(APIView):
    def get(self, request):
        try:
            year = int(request.GET.get("year"))
            month = int(request.GET.get("month"))
        except (TypeError, ValueError):
            return Response({"error": "Invalid or missing 'year' or 'month' parameters."},
                            status=status.HTTP_400_BAD_REQUEST)

        state_name = request.GET.get("state")
        selected_date = date(year, month, 1)

        bands = Band.objects.all()
        results = []

        for band in bands:
            # Get feeders for the band (filtered by state if provided)
            feeders = Feeder.objects.filter(band=band)
            if state_name:
                feeders = feeders.filter(business_district__state__name__iexact=state_name)

            if not feeders.exists():
                continue

            # Get distinct business districts tied to the feeders
            district_ids = feeders.values_list("business_district_id", flat=True).distinct()

            # Get all sales reps tied to feeders via transformers
            sales_reps = SalesRepresentative.objects.filter(
                assigned_transformers__feeder__in=feeders
            ).distinct()

            # Aggregate commercial revenue & collections
            commercial = MonthlyCommercialSummary.objects.filter(
                sales_rep__in=sales_reps,
                month=selected_date
            ).aggregate(
                revenue_billed=Sum("revenue_billed"),
                revenue_collected=Sum("revenue_collected")
            )

            revenue_billed = commercial["revenue_billed"] or Decimal("0")
            revenue_collected = commercial["revenue_collected"] or Decimal("0")

            # Aggregate total cost from expenses (filter by business districts)
            total_cost = Opex.objects.filter(
                district__in=district_ids,
                date__year=year,
                date__month=month
            ).aggregate(total=Sum("credit"))["total"] or Decimal("0")

            # Aggregate energy delivered
            energy_delivered = EnergyDelivered.objects.filter(
                feeder__in=feeders,
                date__year=year,
                date__month=month
            ).aggregate(total_energy=Sum("energy_mwh"))["total_energy"] or Decimal("0")

            # Tariff Calculations
            myto_tariff = Decimal(randint(55, 65))  # Static/random per band
            actual_tariff = (
                round(revenue_collected / energy_delivered, 2)
                if energy_delivered else Decimal("0")
            )
            tariff_loss = round(myto_tariff - actual_tariff, 2)

            results.append({
                "band": band.name,
                "total_cost": round(total_cost, 2),
                "revenue_billed": round(revenue_billed, 2),
                "collections": round(revenue_collected, 2),
                "myto_allowed_tariff": f"{myto_tariff}",
                "actual_tariff_collected": f"{actual_tariff}",
                "tariff_loss": f"{tariff_loss}"
            })

        return Response(results, status=status.HTTP_200_OK)



from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum
from datetime import date, timedelta
from commercial.models import MonthlyCommercialSummary


class DailyCollectionsByMonthView(APIView):
    def get(self, request):
        try:
            year = int(request.GET.get("year"))
            month = int(request.GET.get("month"))
            start_date = date(year, month, 1)
        except (TypeError, ValueError):
            return Response({"error": "Valid 'year' and 'month' query parameters are required."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Get last day of the month
        next_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = next_month - timedelta(days=1)

        results = []

        current_day = start_date
        while current_day <= end_date:
            total_collections = MonthlyCommercialSummary.objects.filter(
                month=current_day
            ).aggregate(
                total=Sum("revenue_collected")
            )["total"] or 0

            results.append({
                "day": current_day.day,
                "value": round(total_collections, 2)
            })

            current_day += timedelta(days=1)

        return Response(results, status=status.HTTP_200_OK)







from rest_framework.decorators import api_view
from rest_framework.response import Response
from commercial.models import MonthlyCommercialSummary, SalesRepresentative
from financial.models import Opex
from common.models import Feeder, DistributionTransformer
from commercial.date_filters import get_date_range_from_request
from datetime import date
from calendar import monthrange
from django.db.models import Sum


@api_view(['GET'])
def financial_transformer_view(request):
    feeder_slug = request.GET.get("feeder")
    mode = request.GET.get("mode", "monthly")
    year = request.GET.get("year")
    month = request.GET.get("month")

    if not feeder_slug:
        return Response({"error": "Missing feeder slug."}, status=400)

    try:
        feeder = Feeder.objects.get(slug=feeder_slug)
    except Feeder.DoesNotExist:
        return Response({"error": "Feeder not found."}, status=404)

    # Handle date filters
    if mode == "monthly" and year and month:
        year = int(year)
        month = int(month)
        start_day = date(year, month, 1)
        end_day = date(year, month, monthrange(year, month)[1])
        date_from, date_to = start_day, end_day
    else:
        date_from, date_to = get_date_range_from_request(request, "date")

    transformer_data = []
    for transformer in feeder.transformers.all():
        reps = SalesRepresentative.objects.filter(
            assigned_transformers=transformer
        ).distinct()

        summary = MonthlyCommercialSummary.objects.filter(
            sales_rep__in=reps,
            month__range=(date_from, date_to)
        ).aggregate(
            revenue_billed=Sum("revenue_billed"),
            revenue_collected=Sum("revenue_collected")
        )

        revenue_billed = summary["revenue_billed"] or 0
        revenue_collected = summary["revenue_collected"] or 0

        total_cost = Opex.objects.filter(
            district=feeder.business_district,
            date__range=(date_from, date_to)
        ).aggregate(total=Sum("credit"))["total"] or 0

        transformer_data.append({
            "transformer": transformer.name,
            "slug": transformer.slug,
            "total_cost": round(total_cost, 2),
            "revenue_billed": round(revenue_billed, 2),
            "revenue_collected": round(revenue_collected, 2),
            "atcc": 6
        })

    return Response({
        "feeder": feeder.name,
        "slug": feeder.slug,
        "transformers": transformer_data
    })
