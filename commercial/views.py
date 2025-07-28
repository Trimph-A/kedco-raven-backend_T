# commercial/views.py
import random
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date, datetime
from dateutil.relativedelta import relativedelta  # type: ignore

from django.db.models import (
    Sum, F, FloatField, ExpressionWrapper, Q,
    Case, When, Value, Count, Avg, DurationField
)
from django.utils.dateparse import parse_date

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import *
from .serializers import *
from .utils import get_filtered_feeders

# from common.models import Feeder, State, BusinessDistrict, Band
from common.models import Feeder, State, BusinessDistrict, Band, DistributionTransformer
from commercial.models import (
    DailyCollection, MonthlyCommercialSummary, MonthlyEnergyBilled
)
from commercial.date_filters import get_date_range_from_request
from commercial.mixins import FeederFilteredQuerySetMixin
from commercial.utils import get_filtered_customers
from commercial.metrics import (
    get_sales_rep_performance_summary
)
from commercial.analytics import get_commercial_overview_data

from technical.models import EnergyDelivered, HourlyLoad, FeederInterruption
from financial.models import MonthlyRevenueBilled, Opex, SalaryPayment, NBETInvoice, MOInvoice

from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend



from decimal import Decimal, ROUND_HALF_UP

def round_two_places(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CustomerViewSet(viewsets.ViewSet):
    """
    Custom ViewSet to return either customer details or just counts
    """

    def list(self, request):
        customers = get_filtered_customers(request)

        # Show full data only if explicitly asked for
        if request.GET.get("details") == "true":
            serializer = CustomerSerializer(customers, many=True)
            return Response(serializer.data)
        else:
            count = customers.count()
            return Response({"count": count})


class DailyEnergyDeliveredViewSet(FeederFilteredQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = DailyEnergyDeliveredSerializer

    def get_queryset(self):
        queryset = DailyEnergyDelivered.objects.all()
        queryset = self.filter_by_location(queryset)
        date_from, date_to = get_date_range_from_request(self.request, 'date')

        if date_from and date_to:
            queryset = queryset.filter(date__range=(date_from, date_to))
        elif date_from:
            queryset = queryset.filter(date__gte=date_from)
        elif date_to:
            queryset = queryset.filter(date__lte=date_to)

        return queryset


# class MonthlyRevenueBilledViewSet(viewsets.ModelViewSet):
#     serializer_class = MonthlyRevenueBilledSerializer

#     def get_queryset(self):
#         queryset = MonthlyRevenueBilled.objects.all()
        
#         # Custom location filtering for MonthlyRevenueBilled
#         state_name = self.request.GET.get('state')
#         district_name = self.request.GET.get('business_district')
#         feeder_slug = self.request.GET.get('feeder')
#         transformer_slug = self.request.GET.get('transformer')

#         if transformer_slug:
#             queryset = queryset.filter(transformer__slug=transformer_slug)
#         elif feeder_slug:
#             queryset = queryset.filter(feeder__slug=feeder_slug)
#         elif district_name:
#             queryset = queryset.filter(feeder__business_district__name__iexact=district_name)
#         elif state_name:
#             queryset = queryset.filter(feeder__business_district__state__name__iexact=state_name)

#         # Date filtering
#         month_from, month_to = get_date_range_from_request(self.request, 'month')

#         if month_from and month_to:
#             queryset = queryset.filter(month__range=(month_from, month_to))
#         elif month_from:
#             queryset = queryset.filter(month__gte=month_from)
#         elif month_to:
#             queryset = queryset.filter(month__lte=month_to)

#         return queryset.select_related(
#             'feeder', 'transformer', 'feeder__business_district',
#             'feeder__business_district__state'
#         )

#     @action(detail=False, methods=['get'])
#     def summary(self, request):
#         """Get revenue billing summary with aggregations"""
#         queryset = self.get_queryset()
        
#         # Basic aggregations
#         summary_data = queryset.aggregate(
#             total_amount=Sum('amount'),
#             total_records=Count('id'),
#             avg_amount=Avg('amount')
#         )

#         # Group by feeder
#         by_feeder = queryset.values(
#             'feeder__name', 'feeder__slug'
#         ).annotate(
#             total=Sum('amount'),
#             count=Count('id')
#         ).order_by('-total')

#         # Group by transformer (if applicable)
#         by_transformer = queryset.filter(
#             transformer__isnull=False
#         ).values(
#             'transformer__name', 'transformer__slug'
#         ).annotate(
#             total=Sum('amount'),
#             count=Count('id')
#         ).order_by('-total')

#         # Group by business district
#         by_district = queryset.values(
#             'feeder__business_district__name'
#         ).annotate(
#             total=Sum('amount'),
#             count=Count('id')
#         ).order_by('-total')

#         # Group by state
#         by_state = queryset.values(
#             'feeder__business_district__state__name'
#         ).annotate(
#             total=Sum('amount'),
#             count=Count('id')
#         ).order_by('-total')

#         return Response({
#             'summary': summary_data,
#             'by_feeder': by_feeder,
#             'by_transformer': by_transformer,
#             'by_district': by_district,
#             'by_state': by_state
#         })

class MonthlyRevenueBilledViewSet(viewsets.ModelViewSet):
    serializer_class = MonthlyRevenueBilledSerializer

    def get_queryset(self):
        queryset = MonthlyRevenueBilled.objects.all()
        
        # Custom location filtering for MonthlyRevenueBilled
        state_name = self.request.GET.get('state')
        district_name = self.request.GET.get('business_district')
        feeder_slug = self.request.GET.get('feeder')
        transformer_slug = self.request.GET.get('transformer')

        if transformer_slug:
            queryset = queryset.filter(transformer__slug=transformer_slug)
        elif feeder_slug:
            queryset = queryset.filter(transformer__feeder__slug=feeder_slug)
        elif district_name:
            queryset = queryset.filter(transformer__feeder__business_district__name__iexact=district_name)
        elif state_name:
            queryset = queryset.filter(transformer__feeder__business_district__state__name__iexact=state_name)

        # Date filtering
        month_from, month_to = get_date_range_from_request(self.request, 'month')

        if month_from and month_to:
            queryset = queryset.filter(month__range=(month_from, month_to))
        elif month_from:
            queryset = queryset.filter(month__gte=month_from)
        elif month_to:
            queryset = queryset.filter(month__lte=month_to)

        return queryset.select_related(
            'transformer', 'transformer__feeder', 'transformer__feeder__business_district',
            'transformer__feeder__business_district__state', 'sales_rep'
        )

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get revenue billing summary with aggregations"""
        queryset = self.get_queryset()
        
        # Basic aggregations
        summary_data = queryset.aggregate(
            total_amount=Sum('amount'),
            total_records=Count('id'),
            avg_amount=Avg('amount')
        )

        # Group by sales rep
        by_sales_rep = queryset.values(
            'sales_rep__name', 'sales_rep__slug'
        ).annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')

        # Group by transformer
        by_transformer = queryset.values(
            'transformer__name', 'transformer__slug'
        ).annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')

        # Group by business district
        by_district = queryset.values(
            'transformer__feeder__business_district__name'
        ).annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')

        # Group by state
        by_state = queryset.values(
            'transformer__feeder__business_district__state__name'
        ).annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')

        return Response({
            'summary': summary_data,
            'by_sales_rep': by_sales_rep,
            'by_transformer': by_transformer,
            'by_district': by_district,
            'by_state': by_state
        })

    # === COLLECTION TOOL INTEGRATION METHODS ===
    
    def resolve_sales_rep_id_to_uuid(self, sales_rep_id):
        """Convert sales_rep_id to SalesRepresentative UUID"""
        if not sales_rep_id or sales_rep_id.strip() == '':
            return None
            
        slug = sales_rep_id.strip()
        try:
            sales_rep = SalesRepresentative.objects.get(slug__iexact=slug)
            print(f"Sales rep '{slug}' resolved to PK: {sales_rep.id}")
            return sales_rep.id
        except SalesRepresentative.DoesNotExist:
            print(f"Sales rep '{slug}' not found")
            return None

    def resolve_dt_id_to_uuid(self, dt_id):
        """Convert dt_id to DistributionTransformer UUID"""
        if not dt_id or dt_id.strip() == '':
            return None
            
        slug = dt_id.strip()
        try:
            transformer = DistributionTransformer.objects.get(slug__iexact=slug)
            print(f"Transformer '{slug}' resolved to PK: {transformer.id}")
            return transformer.id
        except DistributionTransformer.DoesNotExist:
            print(f"Transformer '{slug}' not found")
            return None

    def validate_sales_rep_transformer_assignment(self, sales_rep_id, transformer_id):
        """Validate that sales_rep is assigned to the transformer"""
        try:
            sales_rep = SalesRepresentative.objects.get(id=sales_rep_id)
            transformer = DistributionTransformer.objects.get(id=transformer_id)
            
            if not sales_rep.assigned_transformers.filter(id=transformer_id).exists():
                return False, f"Sales rep '{sales_rep.slug}' is not assigned to transformer '{transformer.slug}'"
            return True, None
        except (SalesRepresentative.DoesNotExist, DistributionTransformer.DoesNotExist):
            return False, "Sales rep or transformer not found"

    def resolve_foreign_keys(self, revenue_item):
        """Resolve all foreign key references from IDs to UUIDs"""
        resolved_data = revenue_item.copy()
        
        # Resolve sales_rep_id
        sales_rep_id = revenue_item.get('sales_rep_id')
        if sales_rep_id:
            sales_rep_pk = self.resolve_sales_rep_id_to_uuid(sales_rep_id)
            if not sales_rep_pk:
                raise ValueError(f"Sales rep ID '{sales_rep_id}' could not be resolved")
            resolved_data['sales_rep'] = sales_rep_pk
        else:
            resolved_data['sales_rep'] = None
        
        # Remove sales_rep_id from final data
        resolved_data.pop('sales_rep_id', None)
        
        # Resolve dt_id to transformer
        dt_id = revenue_item.get('dt_id')
        if dt_id:
            transformer_pk = self.resolve_dt_id_to_uuid(dt_id)
            if not transformer_pk:
                raise ValueError(f"Transformer ID '{dt_id}' could not be resolved")
            resolved_data['transformer'] = transformer_pk
        else:
            resolved_data['transformer'] = None
            
        # Remove dt_id from final data
        resolved_data.pop('dt_id', None)
        
        # Validate assignment during CREATE only
        if resolved_data.get('sales_rep') and resolved_data.get('transformer'):
            is_valid, error_msg = self.validate_sales_rep_transformer_assignment(
                resolved_data['sales_rep'], resolved_data['transformer']
            )
            if not is_valid:
                raise ValueError(error_msg)
        
        return resolved_data

    @action(detail=False, methods=['post'], url_path='upsert-external')
    def upsert_external(self, request):
        external_id = request.data.get("external_id")
        if not external_id:
            return Response({"error": "external_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        instance = MonthlyRevenueBilled.objects.filter(external_id=external_id).first()
        serializer = self.get_serializer(instance, data=request.data, partial=bool(instance))
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK if instance else status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='bulk_create')
    def bulk_create(self, request):
        """Test endpoint to verify URL routing works"""
        return Response({'message': 'URL routing works!', 'viewset': 'MonthlyRevenueBilledViewSet'})

        revenue_data = request.data.get('revenues', [])
        print(f"Received {len(revenue_data)} revenue records for bulk create")
        if not revenue_data:
            return Response({'error': 'No revenue data provided'}, status=status.HTTP_400_BAD_REQUEST)

        created, updated, errors = [], [], []
        with transaction.atomic():
            for idx, revenue_item in enumerate(revenue_data):
                try:
                    print(f"Processing revenue item {idx}: {revenue_item}")
                    
                    # Normalize date
                    if isinstance(revenue_item.get('month'), str) and 'T' in revenue_item['month']:
                        revenue_item['month'] = revenue_item['month'].split('T')[0]

                    # Smart search strategy
                    existing = None
                    external_id = revenue_item.get('external_id')
                    
                    if external_id:
                        # Search by external_id + month
                        precise_search = {
                            'external_id': external_id,
                            'month': revenue_item.get('month')
                        }
                        print(f"Searching by external_id + month: {precise_search}")
                        existing = self.get_queryset().filter(**precise_search).first()
                    
                    # Fallback to composite key search
                    if not existing:
                        search_criteria = {
                            'month': revenue_item.get('month'),
                            'sales_rep__slug': revenue_item.get('sales_rep_id'),
                            'transformer__slug': revenue_item.get('dt_id', '')
                        }
                        print(f"Searching by composite key: {search_criteria}")
                        existing = self.get_queryset().filter(**search_criteria).first()
                    
                    # Resolve foreign keys
                    try:
                        resolved_data = self.resolve_foreign_keys(revenue_item)
                        print(f"Resolved foreign keys: sales_rep={resolved_data.get('sales_rep')}, transformer={resolved_data.get('transformer')}")
                    except ValueError as e:
                        errors.append({'index': idx, 'data': revenue_item, 'errors': str(e)})
                        continue
                    
                    if existing:
                        print(f"UPDATING existing revenue ID: {existing.id}")
                        serializer = self.get_serializer(existing, data=resolved_data, partial=True)
                        if serializer.is_valid():
                            saved_instance = serializer.save()
                            updated.append(serializer.data)
                        else:
                            errors.append({'index': idx, 'data': revenue_item, 'errors': serializer.errors})
                    else:
                        print(f"CREATING new revenue record")
                        serializer = self.get_serializer(data=resolved_data)
                        if serializer.is_valid():
                            saved_instance = serializer.save()
                            created.append(serializer.data)
                        else:
                            errors.append({'index': idx, 'data': revenue_item, 'errors': serializer.errors})
                            
                except Exception as e:
                    print(f"Exception at {idx}: {e}")
                    errors.append({'index': idx, 'data': revenue_item, 'errors': str(e)})

        response_data = {'created': len(created), 'updated': len(updated), 'errors': len(errors),
                         'created_data': created, 'updated_data': updated}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'], url_path='bulk_update')
    def bulk_update(self, request):
        revenue_data = request.data.get('revenues', [])
        print(f"Received {len(revenue_data)} revenue records for bulk update")
        if not revenue_data:
            return Response({'error': 'No revenue data provided'}, status=status.HTTP_400_BAD_REQUEST)

        updated, errors = [], []
        with transaction.atomic():
            for idx, revenue_item in enumerate(revenue_data):
                try:
                    print(f"Processing UPDATE revenue item {idx}: {revenue_item}")
                    
                    # Normalize dates
                    comp = revenue_item.get('_composite_key', {})
                    if comp and isinstance(comp.get('month'), str) and 'T' in comp['month']:
                        comp['month'] = comp['month'].split('T')[0]
                    if isinstance(revenue_item.get('month'), str) and 'T' in revenue_item['month']:
                        revenue_item['month'] = revenue_item['month'].split('T')[0]

                    # Smart search for UPDATE
                    existing = None
                    
                    if comp:
                        data_to_resolve = {**revenue_item}
                        data_to_resolve.update(comp)
                        data_to_resolve.pop('_composite_key', None)
                    else:
                        data_to_resolve = revenue_item
                    
                    external_id = data_to_resolve.get('external_id')
                    if external_id:
                        # Search by external_id + month
                        precise_search = {
                            'external_id': external_id,
                            'month': data_to_resolve.get('month')
                        }
                        print(f"UPDATE: Searching by external_id + month: {precise_search}")
                        existing = self.get_queryset().filter(**precise_search).first()
                    
                    # Fallback to composite key search
                    if not existing:
                        if comp:
                            search_criteria = {
                                'month': comp.get('month'),
                                'sales_rep__slug': comp.get('sales_rep_id'),
                                'transformer__slug': comp.get('dt_id', '')
                            }
                            print(f"UPDATE: Searching by composite key (comp): {search_criteria}")
                        else:
                            search_criteria = {
                                'month': revenue_item.get('month'),
                                'sales_rep__slug': revenue_item.get('sales_rep_id'),
                                'transformer__slug': revenue_item.get('dt_id', '')
                            }
                            print(f"UPDATE: Searching by composite key (direct): {search_criteria}")
                        
                        existing = self.get_queryset().filter(**search_criteria).first()

                    if not existing:
                        print(f"UPDATE: Revenue not found for update")
                        errors.append({'index': idx, 'data': revenue_item, 'errors': 'Revenue not found for update'})
                        continue

                    # Resolve foreign keys
                    try:
                        resolved_data = self.resolve_foreign_keys(data_to_resolve)
                        print(f"UPDATE: Resolved foreign keys: sales_rep={resolved_data.get('sales_rep')}, transformer={resolved_data.get('transformer')}")
                    except ValueError as e:
                        errors.append({'index': idx, 'data': revenue_item, 'errors': str(e)})
                        continue

                    serializer = self.get_serializer(existing, data=resolved_data, partial=True)
                    if serializer.is_valid():
                        saved_instance = serializer.save()
                        print(f"UPDATE: Successfully updated revenue ID: {saved_instance.id}")
                        updated.append(serializer.data)
                    else:
                        print(f"UPDATE: Validation failed: {serializer.errors}")
                        errors.append({'index': idx, 'data': revenue_item, 'errors': serializer.errors})
                        
                except Exception as e:
                    print(f"UPDATE Exception at {idx}: {e}")
                    errors.append({'index': idx, 'data': revenue_item, 'errors': str(e)})

        response_data = {'updated': len(updated), 'errors': len(errors), 'updated_data': updated}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['delete'], url_path='bulk_delete')
    def bulk_delete(self, request):
        revenue_data = request.data.get('revenues', [])
        print(f"Received {len(revenue_data)} revenue records for bulk delete")
        if not revenue_data:
            return Response({'error': 'No revenue data provided'}, status=status.HTTP_400_BAD_REQUEST)

        deleted, errors = 0, []
        with transaction.atomic():
            for idx, revenue_item in enumerate(revenue_data):
                try:
                    print(f"Processing DELETE revenue item {idx}: {revenue_item}")
                    
                    # Normalize dates
                    comp = revenue_item.get('_composite_key', {})
                    if comp and isinstance(comp.get('month'), str) and 'T' in comp['month']:
                        comp['month'] = comp['month'].split('T')[0]
                    if isinstance(revenue_item.get('month'), str) and 'T' in revenue_item['month']:
                        revenue_item['month'] = revenue_item['month'].split('T')[0]

                    # Smart search for DELETE
                    existing = None
                    
                    if comp:
                        search_data = comp
                    else:
                        search_data = revenue_item
                    
                    external_id = search_data.get('external_id')
                    if external_id:
                        # Search by external_id + month
                        precise_search = {
                            'external_id': external_id,
                            'month': search_data.get('month')
                        }
                        print(f"DELETE: Searching by external_id + month: {precise_search}")
                        existing = self.get_queryset().filter(**precise_search).first()
                    
                    # Fallback to composite key search
                    if not existing:
                        if comp:
                            search_criteria = {
                                'month': comp.get('month'),
                                'sales_rep__slug': comp.get('sales_rep_id'),
                                'transformer__slug': comp.get('dt_id', '')
                            }
                            print(f"DELETE: Searching by composite key (comp): {search_criteria}")
                        else:
                            search_criteria = {
                                'month': revenue_item.get('month'),
                                'sales_rep__slug': revenue_item.get('sales_rep_id'),
                                'transformer__slug': revenue_item.get('dt_id', '')
                            }
                            print(f"DELETE: Searching by composite key (direct): {search_criteria}")
                        
                        existing = self.get_queryset().filter(**search_criteria).first()

                    if existing:
                        existing.delete()
                        print(f"DELETE: Successfully deleted revenue")
                        deleted += 1
                    else:
                        print(f"DELETE: Revenue not found for deletion")
                        errors.append({'index': idx, 'data': revenue_item, 'errors': 'Revenue not found for deletion'})
                        
                except Exception as e:
                    print(f"DELETE Exception at {idx}: {e}")
                    errors.append({'index': idx, 'data': revenue_item, 'errors': str(e)})

        response_data = {'deleted': deleted, 'errors': len(errors)}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)

    

# class DailyCollectionViewSet(FeederFilteredQuerySetMixin, viewsets.ModelViewSet):
#     serializer_class = DailyCollectionSerializer

#     def get_queryset(self):
#         queryset = DailyCollection.objects.all()
#         queryset = self.filter_by_location(queryset)
#         date_from, date_to = get_date_range_from_request(self.request, 'date')

#         if date_from and date_to:
#             queryset = queryset.filter(date__range=(date_from, date_to))
#         elif date_from:
#             queryset = queryset.filter(date__gte=date_from)
#         elif date_to:
#             queryset = queryset.filter(date__lte=date_to)

#         # Additional filters
#         collection_type = self.request.GET.get('collection_type')
#         if collection_type:
#             queryset = queryset.filter(collection_type=collection_type)

#         vendor_name = self.request.GET.get('vendor_name')
#         if vendor_name:
#             queryset = queryset.filter(vendor_name=vendor_name)

#         sales_rep_slug = self.request.GET.get('sales_rep')
#         if sales_rep_slug:
#             queryset = queryset.filter(sales_rep__slug=sales_rep_slug)

#         transformer_slug = self.request.GET.get('transformer')
#         if transformer_slug:
#             queryset = queryset.filter(transformer__slug=transformer_slug)

#         return queryset.select_related(
#             'sales_rep', 'transformer', 'transformer__feeder', 
#             'transformer__feeder__business_district', 
#             'transformer__feeder__business_district__state'
#         )

#     def perform_create(self, serializer):
#         """Override to add any additional logic during creation"""
#         serializer.save()

#     @action(detail=False, methods=['get'])
#     def summary(self, request):
#         """Get collection summary with aggregations"""
#         queryset = self.get_queryset()
        
#         # Basic aggregations
#         summary_data = queryset.aggregate(
#             total_amount=Sum('amount'),
#             total_collections=Count('id'),
#             avg_collection=Avg('amount')
#         )

#         # Group by collection type
#         by_type = queryset.values('collection_type').annotate(
#             total=Sum('amount'),
#             count=Count('id')
#         ).order_by('-total')

#         # Group by vendor
#         by_vendor = queryset.values('vendor_name').annotate(
#             total=Sum('amount'),
#             count=Count('id')
#         ).order_by('-total')

#         # Group by sales rep
#         by_sales_rep = queryset.values(
#             'sales_rep__name', 'sales_rep__slug'
#         ).annotate(
#             total=Sum('amount'),
#             count=Count('id')
#         ).order_by('-total')

#         return Response({
#             'summary': summary_data,
#             'by_collection_type': by_type,
#             'by_vendor': by_vendor,
#             'by_sales_rep': by_sales_rep
#         })

class DailyCollectionViewSet(viewsets.ModelViewSet):
    serializer_class = DailyCollectionSerializer

    def get_queryset(self):
        queryset = DailyCollection.objects.all()
        # queryset = self.filter_by_location(queryset)
        date_from, date_to = get_date_range_from_request(self.request, 'date')

        if date_from and date_to:
            queryset = queryset.filter(date__range=(date_from, date_to))
        elif date_from:
            queryset = queryset.filter(date__gte=date_from)
        elif date_to:
            queryset = queryset.filter(date__lte=date_to)

        # Additional filters
        collection_type = self.request.GET.get('collection_type')
        if collection_type:
            queryset = queryset.filter(collection_type=collection_type)

        vendor_name = self.request.GET.get('vendor_name')
        if vendor_name:
            queryset = queryset.filter(vendor_name=vendor_name)

        sales_rep_slug = self.request.GET.get('sales_rep')
        if sales_rep_slug:
            queryset = queryset.filter(sales_rep__slug=sales_rep_slug)

        transformer_slug = self.request.GET.get('transformer')
        if transformer_slug:
            queryset = queryset.filter(transformer__slug=transformer_slug)

        return queryset.select_related(
            'sales_rep', 'transformer', 'transformer__feeder', 
            'transformer__feeder__business_district', 
            'transformer__feeder__business_district__state'
        )

    def perform_create(self, serializer):
        """Override to add any additional logic during creation"""
        serializer.save()

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get collection summary with aggregations"""
        queryset = self.get_queryset()
        
        # Basic aggregations
        summary_data = queryset.aggregate(
            total_amount=Sum('amount'),
            total_collections=Count('id'),
            avg_collection=Avg('amount')
        )

        # Group by collection type
        by_type = queryset.values('collection_type').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')

        # Group by vendor
        by_vendor = queryset.values('vendor_name').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')

        # Group by sales rep
        by_sales_rep = queryset.values(
            'sales_rep__name', 'sales_rep__slug'
        ).annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')

        return Response({
            'summary': summary_data,
            'by_collection_type': by_type,
            'by_vendor': by_vendor,
            'by_sales_rep': by_sales_rep
        })

    # === COLLECTION TOOL INTEGRATION METHODS ===
    
    def resolve_sales_rep_id_to_uuid(self, sales_rep_id):
        """Convert sales_rep_id to SalesRepresentative UUID"""
        if not sales_rep_id or sales_rep_id.strip() == '':
            return None
            
        slug = sales_rep_id.strip()
        try:
            sales_rep = SalesRepresentative.objects.get(slug__iexact=slug)
            print(f"Sales rep '{slug}' resolved to PK: {sales_rep.id}")
            return sales_rep.id
        except SalesRepresentative.DoesNotExist:
            print(f"Sales rep '{slug}' not found")
            return None

    def resolve_dt_id_to_uuid(self, dt_id):
        """Convert dt_id to DistributionTransformer UUID"""
        if not dt_id or dt_id.strip() == '':
            return None
            
        slug = dt_id.strip()
        try:
            transformer = DistributionTransformer.objects.get(slug__iexact=slug)
            print(f"Transformer '{slug}' resolved to PK: {transformer.id}")
            return transformer.id
        except DistributionTransformer.DoesNotExist:
            print(f"Transformer '{slug}' not found")
            return None

    def validate_sales_rep_transformer_assignment(self, sales_rep_id, transformer_id):
        """Validate that sales_rep is assigned to the transformer"""
        try:
            sales_rep = SalesRepresentative.objects.get(id=sales_rep_id)
            transformer = DistributionTransformer.objects.get(id=transformer_id)
            
            if not sales_rep.assigned_transformers.filter(id=transformer_id).exists():
                return False, f"Sales rep '{sales_rep.slug}' is not assigned to transformer '{transformer.slug}'"
            return True, None
        except (SalesRepresentative.DoesNotExist, DistributionTransformer.DoesNotExist):
            return False, "Sales rep or transformer not found"

    def resolve_foreign_keys(self, collection_item):
        """Resolve all foreign key references from IDs to UUIDs"""
        resolved_data = collection_item.copy()
        
        # Resolve sales_rep_id
        sales_rep_id = collection_item.get('sales_rep_id')
        if sales_rep_id:
            sales_rep_pk = self.resolve_sales_rep_id_to_uuid(sales_rep_id)
            if not sales_rep_pk:
                raise ValueError(f"Sales rep ID '{sales_rep_id}' could not be resolved")
            resolved_data['sales_rep'] = sales_rep_pk
        else:
            resolved_data['sales_rep'] = None
        
        # Remove sales_rep_id from final data
        resolved_data.pop('sales_rep_id', None)
        
        # Resolve dt_id to transformer
        dt_id = collection_item.get('dt_id')
        if dt_id:
            transformer_pk = self.resolve_dt_id_to_uuid(dt_id)
            if not transformer_pk:
                raise ValueError(f"Transformer ID '{dt_id}' could not be resolved")
            resolved_data['transformer'] = transformer_pk
        else:
            resolved_data['transformer'] = None
            
        # Remove dt_id from final data
        resolved_data.pop('dt_id', None)
        
        # Validate assignment during CREATE only
        if resolved_data.get('sales_rep') and resolved_data.get('transformer'):
            is_valid, error_msg = self.validate_sales_rep_transformer_assignment(
                resolved_data['sales_rep'], resolved_data['transformer']
            )
            # if not is_valid:
            #     raise ValueError(error_msg)
        
        return resolved_data

    @action(detail=False, methods=['post'], url_path='upsert-external')
    def upsert_external(self, request):
        external_id = request.data.get("external_id")
        if not external_id:
            return Response({"error": "external_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        instance = DailyCollection.objects.filter(external_id=external_id).first()
        serializer = self.get_serializer(instance, data=request.data, partial=bool(instance))
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK if instance else status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='bulk_create')
    def bulk_create(self, request):
        collection_data = request.data.get('collections', [])
        print(f"Received {len(collection_data)} collection records for bulk create")
        if not collection_data:
            return Response({'error': 'No collection data provided'}, status=status.HTTP_400_BAD_REQUEST)

        created, updated, errors = [], [], []
        with transaction.atomic():
            for idx, collection_item in enumerate(collection_data):
                try:
                    print(f"Processing collection item {idx}: {collection_item}")
                    
                    # Normalize date
                    if isinstance(collection_item.get('date'), str) and 'T' in collection_item['date']:
                        collection_item['date'] = collection_item['date'].split('T')[0]

                    # Smart search strategy
                    existing = None
                    external_id = collection_item.get('external_id')
                    
                    if external_id:
                        # Search by external_id + date
                        precise_search = {
                            'external_id': external_id,
                            'date': collection_item.get('date')
                        }
                        print(f"Searching by external_id + date: {precise_search}")
                        existing = self.get_queryset().filter(**precise_search).first()
                    
                    # Fallback to composite key search
                    if not existing:
                        search_criteria = {
                            'date': collection_item.get('date'),
                            'sales_rep__slug': collection_item.get('sales_rep_id'),
                            'transformer__slug': collection_item.get('dt_id', ''),
                            'collection_type': collection_item.get('collection_type', ''),
                            'vendor_name': collection_item.get('vendor_name', '')
                        }
                        print(f"Searching by composite key: {search_criteria}")
                        existing = self.get_queryset().filter(**search_criteria).first()
                    
                    # Resolve foreign keys
                    try:
                        resolved_data = self.resolve_foreign_keys(collection_item)
                        print(f"Resolved foreign keys: sales_rep={resolved_data.get('sales_rep')}, transformer={resolved_data.get('transformer')}")
                    except ValueError as e:
                        errors.append({'index': idx, 'data': collection_item, 'errors': str(e)})
                        continue
                    
                    if existing:
                        print(f"UPDATING existing collection ID: {existing.id}")
                        serializer = self.get_serializer(existing, data=resolved_data, partial=True)
                        if serializer.is_valid():
                            saved_instance = serializer.save()
                            updated.append(serializer.data)
                        else:
                            errors.append({'index': idx, 'data': collection_item, 'errors': serializer.errors})
                    else:
                        print(f"CREATING new collection record")
                        serializer = self.get_serializer(data=resolved_data)
                        if serializer.is_valid():
                            saved_instance = serializer.save()
                            created.append(serializer.data)
                        else:
                            errors.append({'index': idx, 'data': collection_item, 'errors': serializer.errors})
                            
                except Exception as e:
                    print(f"Exception at {idx}: {e}")
                    errors.append({'index': idx, 'data': collection_item, 'errors': str(e)})

        response_data = {'created': len(created), 'updated': len(updated), 'errors': len(errors),
                         'created_data': created, 'updated_data': updated}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'], url_path='bulk_update')
    def bulk_update(self, request):
        collection_data = request.data.get('collections', [])
        print(f"Received {len(collection_data)} collection records for bulk update")
        if not collection_data:
            return Response({'error': 'No collection data provided'}, status=status.HTTP_400_BAD_REQUEST)

        updated, errors = [], []
        with transaction.atomic():
            for idx, collection_item in enumerate(collection_data):
                try:
                    print(f"Processing UPDATE collection item {idx}: {collection_item}")
                    
                    # Normalize dates
                    comp = collection_item.get('_composite_key', {})
                    if comp and isinstance(comp.get('date'), str) and 'T' in comp['date']:
                        comp['date'] = comp['date'].split('T')[0]
                    if isinstance(collection_item.get('date'), str) and 'T' in collection_item['date']:
                        collection_item['date'] = collection_item['date'].split('T')[0]

                    # Smart search for UPDATE
                    existing = None
                    
                    if comp:
                        data_to_resolve = {**collection_item}
                        data_to_resolve.update(comp)
                        data_to_resolve.pop('_composite_key', None)
                    else:
                        data_to_resolve = collection_item
                    
                    external_id = data_to_resolve.get('external_id')
                    if external_id:
                        # Search by external_id + date
                        precise_search = {
                            'external_id': external_id,
                            'date': data_to_resolve.get('date')
                        }
                        print(f"UPDATE: Searching by external_id + date: {precise_search}")
                        existing = self.get_queryset().filter(**precise_search).first()
                    
                    # Fallback to composite key search
                    if not existing:
                        if comp:
                            search_criteria = {
                                'date': comp.get('date'),
                                'sales_rep__slug': comp.get('sales_rep_id'),
                                'transformer__slug': comp.get('dt_id', ''),
                                'collection_type': comp.get('collection_type', ''),
                                'vendor_name': comp.get('vendor_name', '')
                            }
                            print(f"UPDATE: Searching by composite key (comp): {search_criteria}")
                        else:
                            search_criteria = {
                                'date': collection_item.get('date'),
                                'sales_rep__slug': collection_item.get('sales_rep_id'),
                                'transformer__slug': collection_item.get('dt_id', ''),
                                'collection_type': collection_item.get('collection_type', ''),
                                'vendor_name': collection_item.get('vendor_name', '')
                            }
                            print(f"UPDATE: Searching by composite key (direct): {search_criteria}")
                        
                        existing = self.get_queryset().filter(**search_criteria).first()

                    if not existing:
                        print(f"UPDATE: Collection not found for update")
                        errors.append({'index': idx, 'data': collection_item, 'errors': 'Collection not found for update'})
                        continue

                    # Resolve foreign keys
                    try:
                        resolved_data = self.resolve_foreign_keys(data_to_resolve)
                        print(f"UPDATE: Resolved foreign keys: sales_rep={resolved_data.get('sales_rep')}, transformer={resolved_data.get('transformer')}")
                    except ValueError as e:
                        errors.append({'index': idx, 'data': collection_item, 'errors': str(e)})
                        continue

                    serializer = self.get_serializer(existing, data=resolved_data, partial=True)
                    if serializer.is_valid():
                        saved_instance = serializer.save()
                        print(f"UPDATE: Successfully updated collection ID: {saved_instance.id}")
                        updated.append(serializer.data)
                    else:
                        print(f"UPDATE: Validation failed: {serializer.errors}")
                        errors.append({'index': idx, 'data': collection_item, 'errors': serializer.errors})
                        
                except Exception as e:
                    print(f"UPDATE Exception at {idx}: {e}")
                    errors.append({'index': idx, 'data': collection_item, 'errors': str(e)})

        response_data = {'updated': len(updated), 'errors': len(errors), 'updated_data': updated}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['delete'], url_path='bulk_delete')
    def bulk_delete(self, request):
        collection_data = request.data.get('collections', [])
        print(f"Received {len(collection_data)} collection records for bulk delete")
        if not collection_data:
            return Response({'error': 'No collection data provided'}, status=status.HTTP_400_BAD_REQUEST)

        deleted, errors = 0, []
        with transaction.atomic():
            for idx, collection_item in enumerate(collection_data):
                try:
                    print(f"Processing DELETE collection item {idx}: {collection_item}")
                    
                    # Normalize dates
                    comp = collection_item.get('_composite_key', {})
                    if comp and isinstance(comp.get('date'), str) and 'T' in comp['date']:
                        comp['date'] = comp['date'].split('T')[0]
                    if isinstance(collection_item.get('date'), str) and 'T' in collection_item['date']:
                        collection_item['date'] = collection_item['date'].split('T')[0]

                    # Smart search for DELETE
                    existing = None
                    
                    if comp:
                        search_data = comp
                    else:
                        search_data = collection_item
                    
                    external_id = search_data.get('external_id')
                    if external_id:
                        # Search by external_id + date
                        precise_search = {
                            'external_id': external_id,
                            'date': search_data.get('date')
                        }
                        print(f"DELETE: Searching by external_id + date: {precise_search}")
                        existing = self.get_queryset().filter(**precise_search).first()
                    
                    # Fallback to composite key search
                    if not existing:
                        if comp:
                            search_criteria = {
                                'date': comp.get('date'),
                                'sales_rep__slug': comp.get('sales_rep_id'),
                                'transformer__slug': comp.get('dt_id', ''),
                                'collection_type': comp.get('collection_type', ''),
                                'vendor_name': comp.get('vendor_name', '')
                            }
                            print(f"DELETE: Searching by composite key (comp): {search_criteria}")
                        else:
                            search_criteria = {
                                'date': collection_item.get('date'),
                                'sales_rep__slug': collection_item.get('sales_rep_id'),
                                'transformer__slug': collection_item.get('dt_id', ''),
                                'collection_type': collection_item.get('collection_type', ''),
                                'vendor_name': collection_item.get('vendor_name', '')
                            }
                            print(f"DELETE: Searching by composite key (direct): {search_criteria}")
                        
                        existing = self.get_queryset().filter(**search_criteria).first()

                    if existing:
                        existing.delete()
                        print(f"DELETE: Successfully deleted collection")
                        deleted += 1
                    else:
                        print(f"DELETE: Collection not found for deletion")
                        errors.append({'index': idx, 'data': collection_item, 'errors': 'Collection not found for deletion'})
                        
                except Exception as e:
                    print(f"DELETE Exception at {idx}: {e}")
                    errors.append({'index': idx, 'data': collection_item, 'errors': str(e)})

        response_data = {'deleted': deleted, 'errors': len(errors)}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)



class MonthlyEnergyBilledViewSet(FeederFilteredQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = MonthlyEnergyBilledSerializer

    def get_queryset(self):
        queryset = MonthlyEnergyBilled.objects.all()
        queryset = self.filter_by_location(queryset)
        month_from, month_to = get_date_range_from_request(self.request, 'month')

        if month_from and month_to:
            queryset = queryset.filter(month__range=(month_from, month_to))
        elif month_from:
            queryset = queryset.filter(month__gte=month_from)
        elif month_to:
            queryset = queryset.filter(month__lte=month_to)

        return queryset


class MonthlyCustomerStatsViewSet(FeederFilteredQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = MonthlyCustomerStatsSerializer

    def get_queryset(self):
        queryset = MonthlyCustomerStats.objects.all()
        queryset = self.filter_by_location(queryset)
        month_from, month_to = get_date_range_from_request(self.request, 'month')

        if month_from and month_to:
            queryset = queryset.filter(month__range=(month_from, month_to))
        elif month_from:
            queryset = queryset.filter(month__gte=month_from)
        elif month_to:
            queryset = queryset.filter(month__lte=month_to)

        return queryset


# Aggregated Metrics Endpoint
from rest_framework.views import APIView

class FeederMetricsView(APIView):
    def get(self, request):
        month_from = request.GET.get('month_from')
        month_to = request.GET.get('month_to')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        top_n = request.GET.get('top_n')
        bottom_n = request.GET.get('bottom_n')

        if month_from:
            month_from = datetime.strptime(month_from, "%Y-%m-%d").date()
        if month_to:
            month_to = datetime.strptime(month_to, "%Y-%m-%d").date()
        if date_from:
            date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        if date_to:
            date_to = datetime.strptime(date_to, "%Y-%m-%d").date()

        feeders = get_filtered_feeders(request)
        metrics = []

        for feeder in feeders:
            energy_billed = MonthlyEnergyBilled.objects.filter(
                feeder=feeder,
                month__range=(month_from, month_to)
            ).aggregate(total=Sum('energy_mwh'))['total'] or 0

            energy_delivered = DailyEnergyDelivered.objects.filter(
                feeder=feeder,
                date__range=(date_from, date_to)
            ).aggregate(total=Sum('energy_mwh'))['total'] or 0

            # revenue_collected = DailyRevenueCollected.objects.filter(
            #     feeder=feeder,
            #     date__range=(date_from, date_to)
            # ).aggregate(total=Sum('amount'))['total'] or 0
            revenue_collected=0

            revenue_billed = MonthlyRevenueBilled.objects.filter(
                feeder=feeder,
                month__range=(month_from, month_to)
            ).aggregate(total=Sum('amount'))['total'] or 0

            collection_eff = (revenue_collected / revenue_billed) * 100 if revenue_billed else 0
            billing_eff = (energy_billed / energy_delivered) * 100 if energy_delivered else 0
            atc_c = 100 - (billing_eff * collection_eff / 100)

            metrics.append({
                "feeder_id": feeder.id,
                "feeder": feeder.name,
                "energy_billed": energy_billed,
                "energy_delivered": energy_delivered,
                "revenue_collected": revenue_collected,
                "revenue_billed": revenue_billed,
                "collection_efficiency": round(collection_eff, 2),
                "billing_efficiency": round(billing_eff, 2),
                "atc_c": round(atc_c, 2),
            })

        # Sort and slice by ATC&C
        metrics.sort(key=lambda x: x['atc_c'])
        if top_n:
            metrics = metrics[:int(top_n)]
        elif bottom_n:
            metrics = metrics[-int(bottom_n):]

        return Response(metrics)    


class SalesRepresentativeViewSet(viewsets.ModelViewSet):
    queryset = SalesRepresentative.objects.all()
    serializer_class = SalesRepresentativeSerializer


# class SalesRepPerformanceViewSet(viewsets.ModelViewSet):
#     serializer_class = SalesRepPerformanceSerializer

#     def get_queryset(self):
#         qs = SalesRepPerformance.objects.all()
#         sales_rep_slug = self.request.GET.get('sales_rep')

#         if sales_rep_slug:
#             qs = qs.filter(sales_rep__slug=sales_rep_slug)

#         month_from, month_to = get_date_range_from_request(self.request, 'month')
#         if month_from and month_to:
#             qs = qs.filter(month__range=(month_from, month_to))
#         elif month_from:
#             qs = qs.filter(month__gte=month_from)
#         elif month_to:
#             qs = qs.filter(month__lte=month_to)

#         return qs

class SalesRepPerformanceViewSet(viewsets.ModelViewSet):
    serializer_class = SalesRepPerformanceSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['sales_rep', 'transformer', 'month']

    def get_queryset(self):
        qs = SalesRepPerformance.objects.all()
        sales_rep_slug = self.request.GET.get('sales_rep')

        if sales_rep_slug:
            qs = qs.filter(sales_rep__slug=sales_rep_slug)

        month_from, month_to = get_date_range_from_request(self.request, 'month')
        if month_from and month_to:
            qs = qs.filter(month__range=(month_from, month_to))
        elif month_from:
            qs = qs.filter(month__gte=month_from)
        elif month_to:
            qs = qs.filter(month__lte=month_to)

        return qs

    # === COLLECTION TOOL INTEGRATION METHODS ===
    
    def resolve_sales_rep_id_to_uuid(self, sales_rep_id):
        """Convert sales_rep_id to SalesRepresentative UUID"""
        if not sales_rep_id or sales_rep_id.strip() == '':
            return None
            
        slug = sales_rep_id.strip()
        try:
            sales_rep = SalesRepresentative.objects.get(slug__iexact=slug)
            print(f"Sales rep '{slug}' resolved to PK: {sales_rep.id}")
            return sales_rep.id
        except SalesRepresentative.DoesNotExist:
            print(f"Sales rep '{slug}' not found")
            return None

    def resolve_dt_id_to_uuid(self, dt_id):
        """Convert dt_id to DistributionTransformer UUID"""
        if not dt_id or dt_id.strip() == '':
            return None
            
        slug = dt_id.strip()
        try:
            transformer = DistributionTransformer.objects.get(slug__iexact=slug)
            print(f"Transformer '{slug}' resolved to PK: {transformer.id}")
            return transformer.id
        except DistributionTransformer.DoesNotExist:
            print(f"Transformer '{slug}' not found")
            return None

    def validate_sales_rep_transformer_assignment(self, sales_rep_id, transformer_id):
        """Validate that sales_rep is assigned to the transformer"""
        try:
            sales_rep = SalesRepresentative.objects.get(id=sales_rep_id)
            transformer = DistributionTransformer.objects.get(id=transformer_id)
            
            if not sales_rep.assigned_transformers.filter(id=transformer_id).exists():
                return False, f"Sales rep '{sales_rep.slug}' is not assigned to transformer '{transformer.slug}'"
            return True, None
        except (SalesRepresentative.DoesNotExist, DistributionTransformer.DoesNotExist):
            return False, "Sales rep or transformer not found"

    def resolve_foreign_keys(self, performance_item):
        """Resolve all foreign key references from IDs to UUIDs"""
        resolved_data = performance_item.copy()
        
        # Resolve sales_rep_id
        sales_rep_id = performance_item.get('sales_rep_id')
        if sales_rep_id:
            sales_rep_pk = self.resolve_sales_rep_id_to_uuid(sales_rep_id)
            if not sales_rep_pk:
                raise ValueError(f"Sales rep ID '{sales_rep_id}' could not be resolved")
            resolved_data['sales_rep'] = sales_rep_pk
        else:
            resolved_data['sales_rep'] = None
        
        # Remove sales_rep_id from final data
        resolved_data.pop('sales_rep_id', None)
        
        # Resolve dt_id to transformer
        dt_id = performance_item.get('dt_id')
        if dt_id:
            transformer_pk = self.resolve_dt_id_to_uuid(dt_id)
            if not transformer_pk:
                raise ValueError(f"Transformer ID '{dt_id}' could not be resolved")
            resolved_data['transformer'] = transformer_pk
        else:
            resolved_data['transformer'] = None
            
        # Remove dt_id from final data
        resolved_data.pop('dt_id', None)
        
        # Validate assignment during CREATE only
        if resolved_data.get('sales_rep') and resolved_data.get('transformer'):
            is_valid, error_msg = self.validate_sales_rep_transformer_assignment(
                resolved_data['sales_rep'], resolved_data['transformer']
            )
            if not is_valid:
                raise ValueError(error_msg)
        
        return resolved_data

    @action(detail=False, methods=['post'], url_path='upsert-external')
    def upsert_external(self, request):
        external_id = request.data.get("external_id")
        if not external_id:
            return Response({"error": "external_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        instance = SalesRepPerformance.objects.filter(external_id=external_id).first()
        serializer = self.get_serializer(instance, data=request.data, partial=bool(instance))
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK if instance else status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='bulk_create')
    def bulk_create(self, request):
        performance_data = request.data.get('performances', [])
        print(f"Received {len(performance_data)} performance records for bulk create")
        if not performance_data:
            return Response({'error': 'No performance data provided'}, status=status.HTTP_400_BAD_REQUEST)

        created, updated, errors = [], [], []
        with transaction.atomic():
            for idx, performance_item in enumerate(performance_data):
                try:
                    print(f"Processing performance item {idx}: {performance_item}")
                    
                    # Normalize date
                    if isinstance(performance_item.get('month'), str) and 'T' in performance_item['month']:
                        performance_item['month'] = performance_item['month'].split('T')[0]

                    # Smart search strategy
                    existing = None
                    external_id = performance_item.get('external_id')
                    
                    if external_id:
                        # Search by external_id + month
                        precise_search = {
                            'external_id': external_id,
                            'month': performance_item.get('month')
                        }
                        print(f"Searching by external_id + month: {precise_search}")
                        existing = self.get_queryset().filter(**precise_search).first()
                    
                    # Fallback to composite key search
                    if not existing:
                        search_criteria = {
                            'month': performance_item.get('month'),
                            'sales_rep__slug': performance_item.get('sales_rep_id'),
                            'transformer__slug': performance_item.get('dt_id', '')
                        }
                        print(f"Searching by composite key: {search_criteria}")
                        existing = self.get_queryset().filter(**search_criteria).first()
                    
                    # Resolve foreign keys
                    try:
                        resolved_data = self.resolve_foreign_keys(performance_item)
                        print(f"Resolved foreign keys: sales_rep={resolved_data.get('sales_rep')}, transformer={resolved_data.get('transformer')}")
                    except ValueError as e:
                        errors.append({'index': idx, 'data': performance_item, 'errors': str(e)})
                        continue
                    
                    if existing:
                        print(f"UPDATING existing performance ID: {existing.id}")
                        serializer = self.get_serializer(existing, data=resolved_data, partial=True)
                        if serializer.is_valid():
                            saved_instance = serializer.save()
                            updated.append(serializer.data)
                        else:
                            errors.append({'index': idx, 'data': performance_item, 'errors': serializer.errors})
                    else:
                        print(f"CREATING new performance record")
                        serializer = self.get_serializer(data=resolved_data)
                        if serializer.is_valid():
                            saved_instance = serializer.save()
                            created.append(serializer.data)
                        else:
                            errors.append({'index': idx, 'data': performance_item, 'errors': serializer.errors})
                            
                except Exception as e:
                    print(f"Exception at {idx}: {e}")
                    errors.append({'index': idx, 'data': performance_item, 'errors': str(e)})

        response_data = {'created': len(created), 'updated': len(updated), 'errors': len(errors),
                         'created_data': created, 'updated_data': updated}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'], url_path='bulk_update')
    def bulk_update(self, request):
        performance_data = request.data.get('performances', [])
        print(f"Received {len(performance_data)} performance records for bulk update")
        if not performance_data:
            return Response({'error': 'No performance data provided'}, status=status.HTTP_400_BAD_REQUEST)

        updated, errors = [], []
        with transaction.atomic():
            for idx, performance_item in enumerate(performance_data):
                try:
                    print(f"Processing UPDATE performance item {idx}: {performance_item}")
                    
                    # Normalize dates
                    comp = performance_item.get('_composite_key', {})
                    if comp and isinstance(comp.get('month'), str) and 'T' in comp['month']:
                        comp['month'] = comp['month'].split('T')[0]
                    if isinstance(performance_item.get('month'), str) and 'T' in performance_item['month']:
                        performance_item['month'] = performance_item['month'].split('T')[0]

                    # Smart search for UPDATE
                    existing = None
                    
                    if comp:
                        data_to_resolve = {**performance_item}
                        data_to_resolve.update(comp)
                        data_to_resolve.pop('_composite_key', None)
                    else:
                        data_to_resolve = performance_item
                    
                    external_id = data_to_resolve.get('external_id')
                    if external_id:
                        # Search by external_id + month
                        precise_search = {
                            'external_id': external_id,
                            'month': data_to_resolve.get('month')
                        }
                        print(f"UPDATE: Searching by external_id + month: {precise_search}")
                        existing = self.get_queryset().filter(**precise_search).first()
                    
                    # Fallback to composite key search
                    if not existing:
                        if comp:
                            search_criteria = {
                                'month': comp.get('month'),
                                'sales_rep__slug': comp.get('sales_rep_id'),
                                'transformer__slug': comp.get('dt_id', '')
                            }
                            print(f"UPDATE: Searching by composite key (comp): {search_criteria}")
                        else:
                            search_criteria = {
                                'month': performance_item.get('month'),
                                'sales_rep__slug': performance_item.get('sales_rep_id'),
                                'transformer__slug': performance_item.get('dt_id', '')
                            }
                            print(f"UPDATE: Searching by composite key (direct): {search_criteria}")
                        
                        existing = self.get_queryset().filter(**search_criteria).first()

                    if not existing:
                        print(f"UPDATE: Performance not found for update")
                        errors.append({'index': idx, 'data': performance_item, 'errors': 'Performance not found for update'})
                        continue

                    # Resolve foreign keys
                    try:
                        resolved_data = self.resolve_foreign_keys(data_to_resolve)
                        print(f"UPDATE: Resolved foreign keys: sales_rep={resolved_data.get('sales_rep')}, transformer={resolved_data.get('transformer')}")
                    except ValueError as e:
                        errors.append({'index': idx, 'data': performance_item, 'errors': str(e)})
                        continue

                    serializer = self.get_serializer(existing, data=resolved_data, partial=True)
                    if serializer.is_valid():
                        saved_instance = serializer.save()
                        print(f"UPDATE: Successfully updated performance ID: {saved_instance.id}")
                        updated.append(serializer.data)
                    else:
                        print(f"UPDATE: Validation failed: {serializer.errors}")
                        errors.append({'index': idx, 'data': performance_item, 'errors': serializer.errors})
                        
                except Exception as e:
                    print(f"UPDATE Exception at {idx}: {e}")
                    errors.append({'index': idx, 'data': performance_item, 'errors': str(e)})

        response_data = {'updated': len(updated), 'errors': len(errors), 'updated_data': updated}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['delete'], url_path='bulk_delete')
    def bulk_delete(self, request):
        performance_data = request.data.get('performances', [])
        print(f"Received {len(performance_data)} performance records for bulk delete")
        if not performance_data:
            return Response({'error': 'No performance data provided'}, status=status.HTTP_400_BAD_REQUEST)

        deleted, errors = 0, []
        with transaction.atomic():
            for idx, performance_item in enumerate(performance_data):
                try:
                    print(f"Processing DELETE performance item {idx}: {performance_item}")
                    
                    # Normalize dates
                    comp = performance_item.get('_composite_key', {})
                    if comp and isinstance(comp.get('month'), str) and 'T' in comp['month']:
                        comp['month'] = comp['month'].split('T')[0]
                    if isinstance(performance_item.get('month'), str) and 'T' in performance_item['month']:
                        performance_item['month'] = performance_item['month'].split('T')[0]

                    # Smart search for DELETE
                    existing = None
                    
                    if comp:
                        search_data = comp
                    else:
                        search_data = performance_item
                    
                    external_id = search_data.get('external_id')
                    if external_id:
                        # Search by external_id + month
                        precise_search = {
                            'external_id': external_id,
                            'month': search_data.get('month')
                        }
                        print(f"DELETE: Searching by external_id + month: {precise_search}")
                        existing = self.get_queryset().filter(**precise_search).first()
                    
                    # Fallback to composite key search
                    if not existing:
                        if comp:
                            search_criteria = {
                                'month': comp.get('month'),
                                'sales_rep__slug': comp.get('sales_rep_id'),
                                'transformer__slug': comp.get('dt_id', '')
                            }
                            print(f"DELETE: Searching by composite key (comp): {search_criteria}")
                        else:
                            search_criteria = {
                                'month': performance_item.get('month'),
                                'sales_rep__slug': performance_item.get('sales_rep_id'),
                                'transformer__slug': performance_item.get('dt_id', '')
                            }
                            print(f"DELETE: Searching by composite key (direct): {search_criteria}")
                        
                        existing = self.get_queryset().filter(**search_criteria).first()

                    if existing:
                        existing.delete()
                        print(f"DELETE: Successfully deleted performance")
                        deleted += 1
                    else:
                        print(f"DELETE: Performance not found for deletion")
                        errors.append({'index': idx, 'data': performance_item, 'errors': 'Performance not found for deletion'})
                        
                except Exception as e:
                    print(f"DELETE Exception at {idx}: {e}")
                    errors.append({'index': idx, 'data': performance_item, 'errors': str(e)})

        response_data = {'deleted': deleted, 'errors': len(errors)}
        if errors:
            response_data['error_details'] = errors
        return Response(response_data, status=status.HTTP_200_OK)
    

class SalesRepMetricsView(APIView):
    def get(self, request):
        data = get_sales_rep_performance_summary(request)
        return Response(data)


# class DailyCollectionViewSet(viewsets.ModelViewSet):
#     serializer_class = DailyCollectionSerializer

#     def get_queryset(self):
#         feeders = get_filtered_feeders(self.request)
#         date_from, date_to = get_date_range_from_request(self.request, 'date')

#         qs = DailyCollection.objects.filter(feeder__in=feeders)

#         if date_from and date_to:
#             qs = qs.filter(date__range=(date_from, date_to))
#         elif date_from:
#             qs = qs.filter(date__gte=date_from)
#         elif date_to:
#             qs = qs.filter(date__lte=date_to)

#         collection_type = self.request.GET.get('collection_type')
#         if collection_type:
#             qs = qs.filter(collection_type=collection_type)

#         return qs




class CommercialOverviewAPIView(APIView):
    def get(self, request):
        # Parse query parameters
        mode = request.query_params.get('mode', 'monthly')
        year = int(request.query_params.get('year', datetime.today().year))
        month = int(request.query_params.get('month', datetime.today().month))
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')

        # Delegate to analytics logic
        data = get_commercial_overview_data(
            mode=mode,
            year=year,
            month=month,
            from_date=from_date,
            to_date=to_date
        )

        return Response(data)



def round_two_places(val):
    return Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def smart_target(value, variation=0.1):
    try:
        value = Decimal(str(value))  # ensure input is Decimal
        percent_shift = Decimal(str(random.uniform(-variation, variation)))
        return float(round_two_places(value * (Decimal("1") + percent_shift)))
    except:
        return 0  


@api_view(["GET"])
def commercial_all_states_view(request):
    mode = request.query_params.get("mode", "monthly")
    year = int(request.query_params.get("year", date.today().year))
    month = int(request.query_params.get("month", date.today().month))
    from_date = request.query_params.get("from_date")
    to_date = request.query_params.get("to_date")

    if mode == "monthly":
        current_start = date(year, month, 1)
        current_end = current_start + relativedelta(months=1)
        previous_start = current_start - relativedelta(months=1)
        previous_end = current_start
    else:
        current_start = parse_date(from_date) or date.today().replace(day=1)
        current_end = parse_date(to_date) or date.today()
        previous_start = current_start - (current_end - current_start)
        previous_end = current_start

    results = []

    for state in State.objects.all():
        def summary_agg(start, end):
            summaries = MonthlyCommercialSummary.objects.filter(
                sales_rep__assigned_transformers__feeder__business_district__state=state,
                month__gte=start,
                month__lt=end,
            ).distinct()

            billed = summaries.aggregate(Sum("revenue_billed"))["revenue_billed__sum"] or Decimal(0)
            collected = summaries.aggregate(Sum("revenue_collected"))["revenue_collected__sum"] or Decimal(0)
            cust_billed = summaries.aggregate(Sum("customers_billed"))["customers_billed__sum"] or 0
            cust_resp = summaries.aggregate(Sum("customers_responded"))["customers_responded__sum"] or 0

            return billed, collected, cust_billed, cust_resp

        def delivered_agg(start, end):
            return EnergyDelivered.objects.filter(
                feeder__business_district__state=state,
                date__gte=start,
                date__lt=end
            ).aggregate(Sum("energy_mwh"))["energy_mwh__sum"] or Decimal(0)

        # Current
        revenue_billed, revenue_collected, cust_billed, cust_resp = summary_agg(current_start, current_end)
        energy_delivered = delivered_agg(current_start, current_end)
        energy_billed = MonthlyEnergyBilled.objects.filter(
            feeder__business_district__state=state,
            month__gte=current_start,
            month__lt=current_end
        ).aggregate(Sum("energy_mwh"))["energy_mwh__sum"] or Decimal(0)

        # Previous
        prev_billed, prev_collected, prev_cust_billed, prev_cust_resp = summary_agg(previous_start, previous_end)
        prev_delivered = delivered_agg(previous_start, previous_end)
        prev_energy_billed = MonthlyEnergyBilled.objects.filter(
            feeder__business_district__state=state,
            month__gte=previous_start,
            month__lt=previous_end
        ).aggregate(Sum("energy_mwh"))["energy_mwh__sum"] or Decimal(0)

        def calc_efficiencies(billed, collected, delivered, energy_billed):
            try:
                billing_eff = (Decimal(energy_billed) / Decimal(delivered)) * 100 if delivered else Decimal(0)
                collection_eff = (Decimal(collected) / Decimal(billed)) * 100 if billed else Decimal(0)
                atcc = (Decimal(1) - ((billing_eff / 100) * (collection_eff / 100))) * 100
            except (InvalidOperation, ZeroDivisionError):
                billing_eff = collection_eff = atcc = Decimal(0)
            return billing_eff, collection_eff, atcc

        billing_eff, collection_eff, atcc = calc_efficiencies(
            revenue_billed, revenue_collected, energy_delivered, energy_billed
        )
        prev_billing_eff, prev_collection_eff, prev_atcc = calc_efficiencies(
            prev_billed, prev_collected, prev_delivered, prev_energy_billed
        )

        def percentage_delta(current, previous):
            if previous and previous != 0:
                return round(float(((Decimal(current) - Decimal(previous)) / Decimal(previous)) * 100), 2)
            return None

        results.append({
            "state": state.name,
            "energy_delivered": {
                "actual": float(round_two_places(energy_delivered)),
                "delta": percentage_delta(energy_delivered, prev_delivered)
            },
            "energy_billed": {
                "actual": float(round_two_places(energy_billed)),
                "delta": percentage_delta(energy_billed, prev_energy_billed)
            },
            "energy_collected": {
                "actual": float(round_two_places(revenue_collected)),
                "delta": percentage_delta(revenue_collected, prev_collected)
            },
            "atcc": {
                "actual": float(round_two_places(atcc)),
                "delta": percentage_delta(atcc, prev_atcc),
                "target": smart_target(atcc)
            },
            "billing_efficiency": {
                "actual": float(round_two_places(billing_eff)),
                "delta": percentage_delta(billing_eff, prev_billing_eff),
                "target": smart_target(billing_eff)
            },
            "collection_efficiency": {
                "actual": float(round_two_places(collection_eff)),
                "delta": percentage_delta(collection_eff, prev_collection_eff),
                "target": smart_target(collection_eff)
            },
            "customer_response_rate": {
                "actual": float(round_two_places((cust_resp / cust_billed) * 100 if cust_billed else 0)),
                "delta": percentage_delta(
                    (cust_resp / cust_billed * 100 if cust_billed else 0),
                    (prev_cust_resp / prev_cust_billed * 100 if prev_cust_billed else 0)
                ),
                "target": smart_target((cust_resp / cust_billed * 100 if cust_billed else 0))
            },
            "revenue_billed_per_customer": {
                "actual": float(round_two_places(revenue_billed / cust_billed)) if cust_billed else 0,
                "delta": percentage_delta(
                    (revenue_billed / cust_billed) if cust_billed else 0,
                    (prev_billed / prev_cust_billed) if prev_cust_billed else 0
                )
            },
            "collections_per_customer": {
                "actual": float(round_two_places(revenue_collected / cust_billed)) if cust_billed else 0,
                "delta": percentage_delta(
                    (revenue_collected / cust_billed) if cust_billed else 0,
                    (prev_collected / prev_cust_billed) if prev_cust_billed else 0
                )
            },
        })

    return Response(results)



# def round_two_places(value):
#     return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_delta(current, previous):
    if previous in [0, None]:
        return None
    try:
        delta = ((Decimal(current) - Decimal(previous)) / Decimal(previous)) * 100
        return float(round_two_places(delta))
    except Exception:
        return None


@api_view(["GET"])
def commercial_state_metrics_view(request):
    state_name = request.query_params.get("state")
    mode = request.query_params.get("mode", "monthly")
    year = int(request.query_params.get("year", date.today().year))
    month = int(request.query_params.get("month", date.today().month))
    from_date = request.query_params.get("from_date")
    to_date = request.query_params.get("to_date")

    state = State.objects.filter(name__iexact=state_name).first()
    if not state:
        return Response({"error": "Invalid state"}, status=400)

    def generate_month_list(reference_date):
        return [reference_date - relativedelta(months=i) for i in range(4, -1, -1)]

    selected_date = date(year, month, 1) if mode == "monthly" else parse_date(to_date) or date.today()
    months = generate_month_list(selected_date)

    data = []
    previous = None

    for m in months:
        reps = SalesRepresentative.objects.filter(
            assigned_transformers__feeder__business_district__state=state
        ).distinct()

        summaries = MonthlyCommercialSummary.objects.filter(
            sales_rep__in=reps,
            month__year=m.year,
            month__month=m.month,
        )

        delivered = EnergyDelivered.objects.filter(
            feeder__business_district__state=state,
            date__year=m.year,
            date__month=m.month,
        ).aggregate(Sum("energy_mwh"))['energy_mwh__sum'] or Decimal(0)

        totals = summaries.aggregate(
            revenue_collected=Sum("revenue_collected"),
            revenue_billed=Sum("revenue_billed"),
            customers_billed=Sum("customers_billed"),
            customers_responded=Sum("customers_responded"),
        )

        revenue_billed = totals['revenue_billed'] or Decimal(0)
        revenue_collected = totals['revenue_collected'] or Decimal(0)
        cust_billed = totals['customers_billed'] or 1
        cust_resp = totals['customers_responded'] or 0

        # Metrics calculations
        billing_eff = ((revenue_billed / 50) / delivered * 100) if delivered else Decimal(0)
        collection_eff = ((revenue_collected / revenue_billed) * 100) if revenue_billed else Decimal(0)
        atcc = (billing_eff * collection_eff / 100) if billing_eff and collection_eff else Decimal(0)
        energy_collected = (delivered * collection_eff / 100) if delivered else Decimal(0)
        response_rate = (Decimal(cust_resp) / Decimal(cust_billed) * 100) if cust_billed else Decimal(0)
        revenue_per_cust = (revenue_billed / Decimal(cust_billed))
        collection_per_cust = (revenue_collected / Decimal(cust_billed))

        current = {
            "month": m.strftime("%b"),
            "energy_delivered": float(round_two_places(delivered)),
            "revenue_billed": float(round_two_places(revenue_billed)),
            "energy_collected": float(round_two_places(energy_collected)),
            "billing_efficiency": float(round_two_places(billing_eff)),
            "collection_efficiency": float(round_two_places(collection_eff)),
            "atcc": float(round_two_places(atcc)),
            "customer_response_rate": float(round_two_places(response_rate)),
            "revenue_billed_per_customer": float(round_two_places(revenue_per_cust)),
            "collections_per_customer": float(round_two_places(collection_per_cust)),
        }

        if previous:
            current["deltas"] = {
                "energy_delivered": compute_delta(current["energy_delivered"], previous["energy_delivered"]),
                "revenue_billed": compute_delta(current["revenue_billed"], previous["revenue_billed"]),
                "energy_collected": compute_delta(current["energy_collected"], previous["energy_collected"]),
                "billing_efficiency": compute_delta(current["billing_efficiency"], previous["billing_efficiency"]),
                "collection_efficiency": compute_delta(current["collection_efficiency"], previous["collection_efficiency"]),
                "atcc": compute_delta(current["atcc"], previous["atcc"]),
                "customer_response_rate": compute_delta(current["customer_response_rate"], previous["customer_response_rate"]),
                "revenue_billed_per_customer": compute_delta(current["revenue_billed_per_customer"], previous["revenue_billed_per_customer"]),
                "collections_per_customer": compute_delta(current["collections_per_customer"], previous["collections_per_customer"]),
            }

        previous = current
        data.append(current)

    return Response(data)



@api_view(["GET"])
def commercial_all_business_districts_view(request):
    state_name = request.query_params.get("state")
    year = int(request.query_params.get("year", date.today().year))
    month = int(request.query_params.get("month", date.today().month))

    period_start = date(year, month, 1)
    period_end = period_start + relativedelta(months=1)

    districts = BusinessDistrict.objects.filter(state__name__iexact=state_name)
    result = []

    for district in districts:
        # Energy Delivered in MWh
        delivered_mwh = EnergyDelivered.objects.filter(
            feeder__business_district=district,
            date__gte=period_start,
            date__lt=period_end,
        ).aggregate(Sum("energy_mwh"))['energy_mwh__sum'] or Decimal(0)

        # Energy Billed in MWh
        billed_mwh = MonthlyEnergyBilled.objects.filter(
            feeder__business_district=district,
            month__gte=period_start,
            month__lt=period_end,
        ).aggregate(Sum("energy_mwh"))['energy_mwh__sum'] or Decimal(0)


        # Commercial Summary
        feeders = district.feeders.all()
        reps = SalesRepresentative.objects.filter(assigned_transformers__feeder__in=feeders).distinct()
        summaries = MonthlyCommercialSummary.objects.filter(
            sales_rep__in=reps,
            month__gte=period_start,
            month__lt=period_end,
        )

        totals = summaries.aggregate(
            revenue_billed=Sum("revenue_billed"),
            revenue_collected=Sum("revenue_collected"),
            customers_billed=Sum("customers_billed"),
            customers_responded=Sum("customers_responded"),
        )

        billed = totals["revenue_billed"] or Decimal(0)
        collected = totals["revenue_collected"] or Decimal(0)
        cust_billed = totals["customers_billed"] or 1  # prevent divide by zero
        cust_resp = totals["customers_responded"] or 0

        try:
            billing_eff = (billed_mwh / delivered_mwh * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if delivered_mwh else Decimal(0)
            collection_eff = (collected / billed * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if billed else Decimal(0)
            atcc = (Decimal(100) - (billing_eff * collection_eff / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            energy_collected = (delivered_mwh * collection_eff / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if delivered_mwh else Decimal(0)
        except:
            billing_eff = collection_eff = atcc = Decimal(0)

        response_rate = (Decimal(cust_resp) / Decimal(cust_billed) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if cust_billed else Decimal(0)
        revenue_per_customer = (billed / cust_billed).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if cust_billed else Decimal(0)
        collections_per_customer = (collected / cust_billed).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if cust_billed else Decimal(0)

        result.append({
            "name": district.name,
            "energy_delivered": float(delivered_mwh.quantize(Decimal("0.01"))),
            "energy_billed": float(billed_mwh.quantize(Decimal("0.01"))),
            "energy_collected": float(energy_collected),
            "revenue_billed": float(billed.quantize(Decimal("0.01"))),
            "revenue_collected": float(collected.quantize(Decimal("0.01"))),
            "billing_efficiency": float(billing_eff),
            "collection_efficiency": float(collection_eff),
            "atcc": float(atcc),
            "customer_response_rate": float(response_rate),
            "revenue_billed_per_customer": float(revenue_per_customer),
            "collections_per_customer": float(collections_per_customer),
        })

    return Response(result)


# Helper
def NullIfZero(field):
    return Case(
        When(**{f'{field.name}': 0}, then=Value(None)),
        default=field,
        output_field=FloatField(),
    )



@api_view(['GET'])
def feeder_metrics(request):
    feeders = get_filtered_feeders(request)
    date_filter = get_date_range_from_request(request)

    queryset = feeders.filter(**date_filter).annotate(
        energy_delivered=Sum('dailyenergydelivered__energy_mwh'),
        energy_billed=Sum('monthlyenergybilled__energy_mwh'),
        energy_collected=Sum('dailyrevenuecollected__amount'),
        atcc=ExpressionWrapper(
            100 - (
                (100 - F('billing_efficiency')) *
                (100 - F('collection_efficiency')) / 100
            ),
            output_field=FloatField()
        )
    ).values('name', 'energy_delivered', 'energy_billed', 'energy_collected', 'atcc')

    return Response(queryset)



# from django.views.decorators.cache import cache_page
# from django.utils.decorators import method_decorator


# # @method_decorator(cache_page(60 * 5), name='dispatch')
class OverviewAPIView(APIView):
    def get(self, request):
        try:
            month = int(request.GET.get("month"))
            year = int(request.GET.get("year"))
            target = datetime(year, month, 1)
        except (TypeError, ValueError):
            target = None

        from_date_str = request.GET.get("from")
        to_date_str = request.GET.get("to")
        from_date = datetime.strptime(from_date_str, "%Y-%m-%d") if from_date_str else None
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d") if to_date_str else None

        if from_date and to_date:
            current = from_date.replace(day=1)
            months = []
            while current <= to_date:
                months.append(current)
                current += relativedelta(months=1)
        else:
            target = target or datetime.today().replace(day=1)
            months = [(target - relativedelta(months=i)).replace(day=1) for i in range(5)][::-1]

        overview_data = []

        for m in months:
            # Commercial data aggregation
            comm = MonthlyCommercialSummary.objects.filter(month=m).aggregate(
                revenue_billed=Sum("revenue_billed"),
                revenue_collected=Sum("revenue_collected"),
                customers_billed=Sum("customers_billed"),
                customers_responded=Sum("customers_responded"),
            )
            
            # Energy data aggregation
            energy_delivered = EnergyDelivered.objects.filter(
                date__year=m.year, 
                date__month=m.month
            ).aggregate(energy=Sum("energy_mwh"))["energy"] or Decimal("0")
            
            energy_billed = MonthlyEnergyBilled.objects.filter(month=m).aggregate(
                energy=Sum("energy_mwh")
            )["energy"] or Decimal("0")

            # Extract commercial values first
            revenue_billed = comm['revenue_billed'] or Decimal("0")
            revenue_collected = comm['revenue_collected'] or Decimal("0")
            customers_billed = comm['customers_billed'] or 0
            customers_responded = comm['customers_responded'] or 0
            
            # Financial data - include all cost components
            opex_costs = Opex.objects.filter(
                date__year=m.year, 
                date__month=m.month
            ).aggregate(
                total_opex=Sum("credit") + Sum("debit")
            )["total_opex"] or Decimal("0")
            
            # Add other cost components - ensure proper date filtering
            salary_costs = SalaryPayment.objects.filter(
                month__year=m.year,
                month__month=m.month
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
            
            nbet_costs = NBETInvoice.objects.filter(
                month__year=m.year,
                month__month=m.month
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
            
            mo_costs = MOInvoice.objects.filter(
                month__year=m.year,
                month__month=m.month
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
            
            total_cost = opex_costs + salary_costs + nbet_costs + mo_costs
            
            # Check if we have any actual operational data for this month
            has_operational_data = (
                energy_delivered > 0 or 
                revenue_billed > 0 or 
                customers_billed > 0
            )
            
            # If no operational data exists, you might want to set total_cost to 0
            # or handle it differently based on business logic
            if not has_operational_data and total_cost == 0:
                # This month truly has no data
                total_cost = Decimal("0")

            # Technical metrics - improved calculation
            # Calculate average hours of supply more accurately
            hourly_loads = HourlyLoad.objects.filter(
                date__year=m.year, 
                date__month=m.month,
                load_mw__gt=0  # Only count hours with actual load
            ).values('feeder', 'date').annotate(
                daily_hours=Count('hour')
            )
            
            if hourly_loads.exists():
                avg_hours_supply = hourly_loads.aggregate(
                    avg=Avg('daily_hours')
                )["avg"] or 0
            else:
                avg_hours_supply = 0

            # Calculate interruption metrics properly
            interruptions = FeederInterruption.objects.filter(
                occurred_at__year=m.year, 
                occurred_at__month=m.month,
                restored_at__isnull=False
            )
            
            if interruptions.exists():
                total_duration = sum(
                    (interrupt.restored_at - interrupt.occurred_at).total_seconds() / 3600 
                    for interrupt in interruptions
                )
                avg_interruption_duration = total_duration / interruptions.count()
                avg_turnaround_time = avg_interruption_duration  # Same as interruption duration
            else:
                avg_interruption_duration = 0
                avg_turnaround_time = 0

            # Calculate efficiency metrics without tariff
            # Billing efficiency = Energy Billed / Energy Delivered
            billing_eff = (energy_billed / energy_delivered) if energy_delivered > 0 else Decimal("0")
            
            # Collection efficiency = Revenue Collected / Revenue Billed
            collection_eff = (revenue_collected / revenue_billed) if revenue_billed > 0 else Decimal("0")
            
            # AT&C Losses = 100% - (Billing Efficiency × Collection Efficiency)
            atc_losses = Decimal("1") - (billing_eff * collection_eff)
            
            # Energy collected = Energy Delivered × Collection Efficiency
            # This represents the energy equivalent of what was actually collected
            energy_collected = energy_delivered * collection_eff
            
            # Customer response rate
            customer_response_rate = (customers_responded / customers_billed * 100) if customers_billed > 0 else 0

            overview_data.append({
                "month": m.strftime("%b"),
                "billing_efficiency": float(round(billing_eff * 100, 2)),
                "collection_efficiency": float(round(collection_eff * 100, 2)),
                "atcc": float(round(atc_losses * 100, 2)),  # AT&C losses as percentage
                "revenue_billed": float(revenue_billed),
                "revenue_collected": float(revenue_collected),
                "energy_billed": float(energy_billed),
                "energy_delivered": float(energy_delivered),
                "energy_collected": float(round(energy_collected, 2)),
                "customer_response_rate": round(customer_response_rate, 2),
                "total_cost": float(total_cost),
                "avg_hours_supply": round(avg_hours_supply, 2),
                "avg_interruption_duration": round(avg_interruption_duration, 2),
                "avg_turnaround_time": round(avg_turnaround_time, 2),
            })

        # Calculate deltas for current month vs previous month
        current = overview_data[-1] if overview_data else {}
        previous = overview_data[-2] if len(overview_data) > 1 else {}

        def calculate_delta(metric):
            """Calculate percentage change between current and previous values"""
            if (metric in current and metric in previous and 
                previous[metric] is not None and previous[metric] != 0):
                return round(((current[metric] - previous[metric]) / previous[metric]) * 100, 2)
            return None

        # Add delta calculations for all metrics
        metrics_to_track = [
            "atcc", "billing_efficiency", "collection_efficiency",
            "revenue_billed", "revenue_collected", "energy_billed", 
            "energy_delivered", "total_cost", "energy_collected",
            "customer_response_rate", "avg_hours_supply",
            "avg_interruption_duration", "avg_turnaround_time"
        ]

        for metric in metrics_to_track:
            current[f"delta_{metric}"] = calculate_delta(metric)

        return Response({
            "current": current,
            "history": overview_data[:-1]  # All months except current
        })


def calculate_atcc_metrics(feeder, start_date, end_date):
    delivered = EnergyDelivered.objects.filter(
        feeder=feeder,
        date__gte=start_date,
        date__lt=end_date
    ).aggregate(energy_mwh_sum=Sum("energy_mwh"))['energy_mwh_sum'] or Decimal(0)

    billed = MonthlyEnergyBilled.objects.filter(
        feeder=feeder,
        month__gte=start_date,
        month__lt=end_date
    ).aggregate(energy_mwh_sum=Sum("energy_mwh"))['energy_mwh_sum'] or Decimal(0)

    summaries = MonthlyCommercialSummary.objects.filter(
        sales_rep__assigned_transformers__feeder=feeder,
        month__gte=start_date,
        month__lt=end_date
    ).aggregate(
        revenue_collected_sum=Sum("revenue_collected"), 
        revenue_billed_sum=Sum("revenue_billed")
    )

    revenue_collected = summaries["revenue_collected_sum"] or Decimal(0)
    revenue_billed = summaries["revenue_billed_sum"] or Decimal(1)

    try:
        billing_eff = (billed / delivered * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if delivered else Decimal(0)
        collection_eff = (revenue_collected / revenue_billed * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if revenue_billed else Decimal(0)
        atcc = (Decimal(100) - (billing_eff * collection_eff / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        collected_energy = (delivered * collection_eff / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except:
        billing_eff = collection_eff = atcc = collected_energy = Decimal(0)

    return {
        "name": feeder.name,
        "energy_delivered": float(delivered),
        "energy_billed": float(billed),
        "energy_collected": float(collected_energy),
        "atcc": float(atcc),
        "voltage_level": feeder.voltage_level,
    }


@api_view(["GET"])
def feeder_performance_view(request):
    year = int(request.query_params.get("year", date.today().year))
    month = int(request.query_params.get("month", date.today().month))
    start_date = date(year, month, 1)
    end_date = start_date + relativedelta(months=1)

    feeders = Feeder.objects.all()
    feeder_data = []

    for feeder in feeders:
        metrics = calculate_atcc_metrics(feeder, start_date, end_date)
        feeder_data.append(metrics)

    sorted_by_atcc = sorted(feeder_data, key=lambda x: x["atcc"])
    return Response({
        "top_5": sorted_by_atcc[:5],
        "bottom_5": sorted_by_atcc[-5:][::-1]
    })


@api_view(["GET"])
def feeders_by_location_view(request):
    state_name = request.query_params.get("state")
    district_name = request.query_params.get("business_district")
    year = int(request.query_params.get("year", date.today().year))
    month = int(request.query_params.get("month", date.today().month))
    start_date = date(year, month, 1)
    end_date = start_date + relativedelta(months=1)

    filters = Q()

    if district_name:
        filters = Q(business_district__name__iexact=district_name)
    elif state_name:
        state = State.objects.filter(name__iexact=state_name).first()
        if not state:
            return Response({"error": "Invalid state"}, status=400)
        filters = Q(business_district__state=state)

    feeders = Feeder.objects.filter(filters)
    result = []

    for feeder in feeders:
        metrics = calculate_atcc_metrics(feeder, start_date, end_date)

        result.append({
            "name": feeder.name,
            "slug": feeder.slug,
            "voltage_level": feeder.voltage_level,
            "business_district": {
                "name": feeder.business_district.name if feeder.business_district else None,
                "slug": feeder.business_district.slug if feeder.business_district else None,
            },
            **metrics  # Unpack and merge the calculated metrics directly into the top-level dict
        })

    return Response(result)

from calendar import monthrange

@api_view(["GET"])
def transformer_metrics_by_feeder_view(request):
    feeder_slug = request.GET.get("feeder")
    if not feeder_slug:
        return Response({"error": "Missing feeder slug in query parameters"}, status=400)

    try:
        feeder = Feeder.objects.get(slug=feeder_slug)
    except Feeder.DoesNotExist:
        return Response({"error": "Feeder not found"}, status=404)

    transformers = DistributionTransformer.objects.filter(feeder=feeder)

    mode = request.GET.get("mode", "monthly")
    year = request.GET.get("year")
    month = request.GET.get("month")

    if mode == "monthly" and year and month:
        year = int(year)
        month = int(month)
        start_day = date(year, month, 1)
        end_day = date(year, month, monthrange(year, month)[1])
        date_from, date_to = start_day, end_day
    else:
        date_from, date_to = get_date_range_from_request(request, "date")

    result = []

    for transformer in transformers:
        sales_reps = SalesRepresentative.objects.filter(
            assigned_transformers=transformer
        ).distinct()

        summary = MonthlyCommercialSummary.objects.filter(
            sales_rep__in=sales_reps,
            month__range=(date_from, date_to)
        ).aggregate(
            revenue_billed=Sum("revenue_billed"),
            revenue_collected=Sum("revenue_collected")
        )

        revenue_billed = Decimal(summary["revenue_billed"] or 0)
        revenue_collected = Decimal(summary["revenue_collected"] or 0)

        energy_billed = MonthlyEnergyBilled.objects.filter(
            feeder=feeder,
            month__range=(date_from, date_to)
        ).aggregate(energy=Sum("energy_mwh"))["energy"] or 0

        energy_delivered = EnergyDelivered.objects.filter(
            feeder=feeder,
            date__range=(date_from, date_to)
        ).aggregate(energy=Sum("energy_mwh"))["energy"] or 0

        total_cost = Opex.objects.filter(
            district=transformer.feeder.business_district,
            date__range=(date_from, date_to)
        ).aggregate(total=Sum("credit"))["total"] or 0

        # Calculate ATCC
        try:
            billing_eff = Decimal(energy_billed) / Decimal(energy_delivered) if energy_delivered else Decimal(0)
            collection_eff = revenue_collected / revenue_billed if revenue_billed else Decimal(0)
            atcc = (1 - (billing_eff * collection_eff)) * 100
        except Exception:
            atcc = 0

        result.append({
            "name": transformer.name,
            "slug": transformer.slug,
            "total_cost": round(total_cost, 2),
            "revenue_billed": round(revenue_billed, 2),
            "revenue_collected": round(revenue_collected, 2),
            "atcc": round(atcc, 2),
        })

    return Response(result)


class CustomerBusinessMetricsView(APIView):
    def get(self, request):
        year = int(request.GET.get("year"))
        month = int(request.GET.get("month"))
        state = request.GET.get("state")
        district = request.GET.get("business_district")

        # Build list of 5 months: current + 4 previous
        base_date = date(year, month, 1)
        month_list = [base_date - relativedelta(months=i) for i in reversed(range(5))]

        # Filter queryset by location
        qs = MonthlyCommercialSummary.objects.filter(month__in=month_list)

        if district:
            qs = qs.filter(sales_rep__assigned_transformers__feeder__business_district__name=district)
        elif state:
            qs = qs.filter(sales_rep__assigned_transformers__feeder__business_district__state__name=state)

        results = {
            "customer_response_rate": [],
            "customer_response_metric": [],
            "revenue_billed_per_customer": [],
            "collections_per_customer": []
        }

        for month in month_list:
            data = qs.filter(month=month).aggregate(
                total_customers_billed=Sum("customers_billed"),
                total_customers_responded=Sum("customers_responded"),
                total_revenue_billed=Sum("revenue_billed"),
                total_collections=Sum("revenue_collected")
            )

            # Calculate metrics
            billed = data["total_customers_billed"] or 0
            responded = data["total_customers_responded"] or 0
            revenue = data["total_revenue_billed"] or 0
            collected = data["total_collections"] or 0

            response_rate = round((responded / billed) * 100, 2) if billed else 0
            response_metric = round(responded / billed, 2) if billed else 0
            revenue_per_customer = round(revenue / billed / 1000, 2) if billed else 0  # in '000
            collection_per_customer = round(collected / billed / 1000, 2) if billed else 0  # in '000

            results["customer_response_rate"].append({
                "month": month.strftime("%b"),
                "value": f"{response_rate}%"
            })

            results["customer_response_metric"].append({
                "month": month.strftime("%b"),
                "value": response_metric
            })

            results["revenue_billed_per_customer"].append({
                "month": month.strftime("%b"),
                "value": revenue_per_customer
            })

            results["collections_per_customer"].append({
                "month": month.strftime("%b"),
                "value": collection_per_customer
            })



            energy_data = {
                "energy_delivered": [],
                "energy_billed": [],
                "energy_collected": [],
                "atcc": [],
                "billing_efficiency": [],
                "collection_efficiency": []
            }

            previous_values = {}

            for month in month_list:
                # Get month boundaries
                month_start = month
                next_month = month + relativedelta(months=1)

                # Filter by district or state
                if district:
                    feeder_filter = {
                        "feeder__business_district__name": district
                    }
                elif state:
                    feeder_filter = {
                        "feeder__business_district__state__name": state
                    }
                else:
                    feeder_filter = {}

                # Energy Delivered (Daily)
                ed = EnergyDelivered.objects.filter(
                    date__gte=month_start, date__lt=next_month,
                    **feeder_filter
                ).aggregate(total=Sum("energy_mwh"))["total"] or 0

                # Energy Billed (Monthly)
                eb = MonthlyEnergyBilled.objects.filter(
                    month=month,
                    **feeder_filter
                ).aggregate(total=Sum("energy_mwh"))["total"] or 0

                # Revenue Billed & Collected (Daily)

                # Get the relevant sales reps first
                rep_filter = {}
                if district:
                    rep_filter["assigned_transformers__feeder__business_district__name"] = district
                elif state:
                    rep_filter["assigned_transformers__feeder__business_district__state__name"] = state

                sales_reps = SalesRepresentative.objects.filter(**rep_filter).distinct()

                # Then filter summaries by those reps and month
                revenue_billed = MonthlyCommercialSummary.objects.filter(
                    sales_rep__in=sales_reps,
                    month=month
                ).aggregate(
                    billed=Sum("revenue_billed"),
                    collected=Sum("revenue_collected")
                )

                rb = revenue_billed["billed"] or 0
                rc = revenue_billed["collected"] or 0

            

                # Efficiency Metrics
                billing_eff = (eb / ed) * 100 if ed else 0
                collection_eff = (rc / rb) * 100 if rb else 0
                atcc = 100 - (billing_eff * collection_eff / 100) if billing_eff and collection_eff else 100
                ec = (Decimal(collection_eff) / Decimal("100")) * Decimal(eb)

                def format_metric(metric_name, value):
                    month_str = month.strftime("%b")
                    prev = previous_values.get(metric_name)
                    delta = round(((value - prev) / prev) * 100, 2) if prev and prev != 0 else None
                    previous_values[metric_name] = value
                    return {
                        "month": month_str,
                        "value": round(value, 2),
                        "delta": delta
                    }

                energy_data["energy_delivered"].append(format_metric("energy_delivered", ed))
                energy_data["energy_billed"].append(format_metric("energy_billed", eb))
                energy_data["energy_collected"].append(format_metric("energy_collected", ec))
                energy_data["billing_efficiency"].append(format_metric("billing_efficiency", billing_eff))
                energy_data["collection_efficiency"].append(format_metric("collection_efficiency", collection_eff))
                energy_data["atcc"].append(format_metric("atcc", atcc))

        
        results.update(energy_data)
        return Response(results, status=status.HTTP_200_OK)

class ServiceBandMetricsView(APIView):
    def get(self, request):
        year = int(request.GET.get("year"))
        month = int(request.GET.get("month"))
        state = request.GET.get("state")

        # Target month
        month_start = date(year, month, 1)
        month_end = month_start + relativedelta(months=1)

        results = []

        for band in Band.objects.all().order_by("name"):
            # Shared filter across models
            band_filter = {"feeder__band": band}

            if state:
                band_filter["feeder__business_district__state__name"] = state


            # ENERGY DELIVERED (Daily)
            energy_delivered = EnergyDelivered.objects.filter(
                date__gte=month_start, date__lt=month_end,
                **band_filter
            ).aggregate(total=Sum("energy_mwh"))["total"] or Decimal("0")

            # ENERGY BILLED (Monthly)
            energy_billed = MonthlyEnergyBilled.objects.filter(
                month=month_start,
                **band_filter
            ).aggregate(total=Sum("energy_mwh"))["total"] or Decimal("0")

            # COMMERCIAL SUMMARY (Monthly)
            commercial_data = MonthlyCommercialSummary.objects.filter(
                month=month_start,
                sales_rep__assigned_transformers__feeder__band=band,
                sales_rep__assigned_transformers__feeder__business_district__state__name=state if state else None
            ).aggregate(
                revenue_billed=Sum("revenue_billed"),
                revenue_collected=Sum("revenue_collected"),
                customers_billed=Sum("customers_billed"),
                customers_responded=Sum("customers_responded")
            )

            revenue_billed = commercial_data["revenue_billed"] or Decimal("0")
            revenue_collected = commercial_data["revenue_collected"] or Decimal("0")
            customers_billed = commercial_data["customers_billed"] or 0
            customers_responded = commercial_data["customers_responded"] or 0

            # Derived Metrics
            billing_eff = (energy_billed / energy_delivered * 100) if energy_delivered else 0
            collection_eff = (revenue_collected / revenue_billed * 100) if revenue_billed else 0
            atc_c = 100 - (billing_eff * collection_eff / 100) if billing_eff and collection_eff else 100
            response_rate = (customers_responded / customers_billed * 100) if customers_billed else 0
            energy_collected = energy_billed * (Decimal(collection_eff) / Decimal("100")) if energy_billed else 0

            results.append({
                "band": band.name,
                "energy_delivered": round(energy_delivered, 2),
                "energy_billed": round(energy_billed, 2),
                "energy_collected": round(energy_collected, 2),
                "atc_c": round(atc_c, 2),
                "billing_efficiency": round(billing_eff, 2),
                "collection_efficiency": round(collection_eff, 2),
                "customer_response_rate": round(response_rate, 2)
            })

        return Response(results, status=status.HTTP_200_OK)
