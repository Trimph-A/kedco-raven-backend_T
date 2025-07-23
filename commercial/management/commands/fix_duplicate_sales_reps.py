# commercial/management/commands/fix_duplicate_sales_reps.py

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q
from collections import defaultdict
from commercial.models import SalesRepresentative, MonthlyCommercialSummary, DailyCollection, DailyRevenueCollected, MonthlyRevenueBilled

class Command(BaseCommand):
    help = 'Fix duplicate sales representatives by merging them and consolidating their assigned transformers'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force the operation without confirmation',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']

        self.stdout.write(self.style.SUCCESS('Starting duplicate sales rep fix...'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Find duplicate sales reps by name
        duplicate_groups = self.find_duplicate_sales_reps()
        
        if not duplicate_groups:
            self.stdout.write(self.style.SUCCESS('No duplicate sales representatives found!'))
            return
        
        self.stdout.write(f'Found {len(duplicate_groups)} groups of duplicate sales reps:')
        
        total_duplicates = 0
        for name, reps in duplicate_groups.items():
            total_duplicates += len(reps) - 1  # Subtract 1 because we keep one
            self.stdout.write(f'  - "{name}": {len(reps)} duplicates')
            for rep in reps:
                transformers = rep.assigned_transformers.all()
                self.stdout.write(f'    * {rep.slug} - {transformers.count()} transformers')
        
        if not force and not dry_run:
            confirm = input(f'\nThis will merge {total_duplicates} duplicate sales reps. Continue? (y/N): ')
            if confirm.lower() != 'y':
                self.stdout.write('Operation cancelled.')
                return
        
        # Process each group of duplicates
        for name, reps in duplicate_groups.items():
            self.merge_duplicate_sales_reps(name, reps, dry_run)
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS('DRY RUN COMPLETE - No changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('Duplicate sales reps have been successfully merged!'))

    def find_duplicate_sales_reps(self):
        """Find all sales reps with duplicate names"""
        # Get all sales reps grouped by name
        sales_reps_by_name = defaultdict(list)
        
        for rep in SalesRepresentative.objects.all().prefetch_related('assigned_transformers'):
            sales_reps_by_name[rep.name].append(rep)
        
        # Filter to only groups with duplicates
        duplicate_groups = {
            name: reps for name, reps in sales_reps_by_name.items() 
            if len(reps) > 1
        }
        
        return duplicate_groups

    def merge_duplicate_sales_reps(self, name, duplicate_reps, dry_run=False):
        """Merge duplicate sales reps into one"""
        self.stdout.write(f'\nProcessing: {name}')
        
        # Sort by creation date to keep the oldest one
        duplicate_reps.sort(key=lambda x: x.created_at if hasattr(x, 'created_at') else x.id)
        primary_rep = duplicate_reps[0]
        duplicates_to_merge = duplicate_reps[1:]
        
        self.stdout.write(f'  Primary rep: {primary_rep.slug}')
        self.stdout.write(f'  Merging {len(duplicates_to_merge)} duplicates')
        
        if dry_run:
            self._show_dry_run_details(primary_rep, duplicates_to_merge)
            return
        
        with transaction.atomic():
            try:
                # 1. Move all transformers to the primary rep
                self._merge_transformers(primary_rep, duplicates_to_merge)
                
                # 2. Merge MonthlyCommercialSummary records
                self._merge_monthly_commercial_summaries(primary_rep, duplicates_to_merge)
                
                # 3. Update other related models
                self._update_related_models(primary_rep, duplicates_to_merge)
                
                # 4. Delete the duplicate reps
                for dup_rep in duplicates_to_merge:
                    self.stdout.write(f'    Deleting duplicate: {dup_rep.slug}')
                    dup_rep.delete()
                
                self.stdout.write(self.style.SUCCESS(f'  ✓ Successfully merged {name}'))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Error merging {name}: {str(e)}'))
                raise

    def _show_dry_run_details(self, primary_rep, duplicates_to_merge):
        """Show what would happen in dry run mode"""
        # Count transformers
        total_transformers = primary_rep.assigned_transformers.count()
        for dup in duplicates_to_merge:
            total_transformers += dup.assigned_transformers.count()
        
        # Count related records
        monthly_summaries = 0
        daily_collections = 0
        daily_revenue = 0
        monthly_revenue = 0
        
        for rep in [primary_rep] + duplicates_to_merge:
            monthly_summaries += MonthlyCommercialSummary.objects.filter(sales_rep=rep).count()
            daily_collections += DailyCollection.objects.filter(sales_rep=rep).count()
            
            # Check if fields exist before counting
            try:
                daily_revenue += DailyRevenueCollected.objects.filter(sales_rep=rep).count()
            except:
                pass  # Field doesn't exist yet
            
            try:
                monthly_revenue += MonthlyRevenueBilled.objects.filter(sales_rep=rep).count()
            except:
                pass  # Field doesn't exist yet
        
        self.stdout.write(f'    Would merge {total_transformers} transformers')
        self.stdout.write(f'    Would consolidate {monthly_summaries} monthly summaries')
        self.stdout.write(f'    Would update {daily_collections} daily collections')
        if daily_revenue > 0:
            self.stdout.write(f'    Would update {daily_revenue} daily revenue records')
        if monthly_revenue > 0:
            self.stdout.write(f'    Would update {monthly_revenue} monthly revenue records')

    def _merge_transformers(self, primary_rep, duplicates_to_merge):
        """Move all transformers from duplicates to primary rep"""
        for dup_rep in duplicates_to_merge:
            transformers = dup_rep.assigned_transformers.all()
            self.stdout.write(f'    Moving {transformers.count()} transformers from {dup_rep.slug}')
            
            for transformer in transformers:
                # Check if primary rep already has this transformer
                if not primary_rep.assigned_transformers.filter(id=transformer.id).exists():
                    primary_rep.assigned_transformers.add(transformer)
                dup_rep.assigned_transformers.remove(transformer)

    def _merge_monthly_commercial_summaries(self, primary_rep, duplicates_to_merge):
        """Merge MonthlyCommercialSummary records, handling unique constraint"""
        for dup_rep in duplicates_to_merge:
            summaries = MonthlyCommercialSummary.objects.filter(sales_rep=dup_rep)
            
            for summary in summaries:
                # Check if primary rep already has a summary for this month
                existing_summary = MonthlyCommercialSummary.objects.filter(
                    sales_rep=primary_rep,
                    month=summary.month
                ).first()
                
                if existing_summary:
                    # Merge the data
                    self.stdout.write(f'    Merging monthly summary for {summary.month}')
                    existing_summary.customers_billed += summary.customers_billed
                    existing_summary.customers_responded += summary.customers_responded
                    existing_summary.revenue_billed += summary.revenue_billed
                    existing_summary.revenue_collected += summary.revenue_collected
                    existing_summary.save()
                    
                    # Delete the duplicate summary
                    summary.delete()
                else:
                    # Just reassign to primary rep
                    self.stdout.write(f'    Moving monthly summary for {summary.month}')
                    summary.sales_rep = primary_rep
                    summary.save()

    def _update_related_models(self, primary_rep, duplicates_to_merge):
        """Update other models that reference the duplicate sales reps"""
        for dup_rep in duplicates_to_merge:
            # Update DailyCollection
            daily_collections = DailyCollection.objects.filter(sales_rep=dup_rep)
            count = daily_collections.count()
            if count > 0:
                self.stdout.write(f'    Updating {count} daily collections')
                daily_collections.update(sales_rep=primary_rep)
            
            # Skip DailyRevenueCollected if it doesn't have sales_rep field yet
            try:
                daily_revenue = DailyRevenueCollected.objects.filter(sales_rep=dup_rep)
                count = daily_revenue.count()
                if count > 0:
                    self.stdout.write(f'    Updating {count} daily revenue records')
                    daily_revenue.update(sales_rep=primary_rep)
            except Exception as e:
                self.stdout.write(f'    Skipping DailyRevenueCollected (field not found): {str(e)}')
            
            # Skip MonthlyRevenueBilled if it doesn't have sales_rep field yet
            try:
                monthly_revenue = MonthlyRevenueBilled.objects.filter(sales_rep=dup_rep)
                count = monthly_revenue.count()
                if count > 0:
                    self.stdout.write(f'    Updating {count} monthly revenue records')
                    monthly_revenue.update(sales_rep=primary_rep)
            except Exception as e:
                self.stdout.write(f'    Skipping MonthlyRevenueBilled (field not found): {str(e)}')