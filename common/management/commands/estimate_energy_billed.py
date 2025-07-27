# management/commands/estimate_energy_billed.py

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum
from django.db import transaction
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime
from dateutil.relativedelta import relativedelta # type: ignore
from tqdm import tqdm # type: ignore

from common.models import Feeder
from commercial.models import MonthlyEnergyBilled
from technical.models import EnergyDelivered


class Command(BaseCommand):
    help = 'Estimate and populate MonthlyEnergyBilled data using proportional allocation'

    # Energy billed data in GWh by year and month
    ENERGY_BILLED_DATA = {
        2022: [140.9, 126.0, 105.0, 109.0, 96.0, 86.0, 101.0, 116.0, 104.0, 112.0, 125.8, 124.1],
        2023: [118.7, 114.4, 134.9, 103.7, 104.4, 95.9, 95.6, 97.5, 99.2, 109.0, 124.6, 128.3],
        2024: [116.0, 102.8, 111.1, 103.4, 122.0, 106.2, 136.9, 137.8, 141.2, 85.0, 80.3, 109.2],
        2025: [99.9, 104.0, 140.8, 134.5],
    }

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            help='Specific year to process (e.g., 2024)',
        )
        parser.add_argument(
            '--month',
            type=int,
            help='Specific month to process (1-12). Requires --year.',
        )
        parser.add_argument(
            '--feeder',
            type=str,
            help='Specific feeder slug to process',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite existing records',
        )

    def handle(self, *args, **options):
        self.dry_run = options.get('dry_run', False)
        self.force = options.get('force', False)
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        try:
            if options.get('year') and options.get('month'):
                # Process specific year and month
                self.process_specific_month(options['year'], options['month'], options.get('feeder'))
            elif options.get('year'):
                # Process entire year
                self.process_year(options['year'], options.get('feeder'))
            else:
                # Process all available data
                self.process_all_data(options.get('feeder'))
                
        except Exception as e:
            raise CommandError(f'Error during processing: {str(e)}')

    def process_all_data(self, feeder_slug=None):
        """Process all available energy billed data"""
        self.stdout.write(self.style.HTTP_INFO("Processing all available energy billed data..."))
        
        total_processed = 0
        total_created = 0
        total_updated = 0
        total_skipped = 0

        for year, monthly_data in self.ENERGY_BILLED_DATA.items():
            self.stdout.write(f"\nProcessing year {year}...")
            
            year_stats = self.process_year(year, feeder_slug)
            total_processed += year_stats['processed']
            total_created += year_stats['created']
            total_updated += year_stats['updated']
            total_skipped += year_stats['skipped']

        self.print_summary(total_processed, total_created, total_updated, total_skipped)

    def process_year(self, year, feeder_slug=None):
        """Process all months in a specific year"""
        if year not in self.ENERGY_BILLED_DATA:
            raise CommandError(f"No energy billed data available for year {year}")

        monthly_data = self.ENERGY_BILLED_DATA[year]
        
        total_processed = 0
        total_created = 0
        total_updated = 0
        total_skipped = 0

        for month_index, energy_gwh in enumerate(monthly_data, 1):
            month_stats = self.process_specific_month(year, month_index, feeder_slug)
            total_processed += month_stats['processed']
            total_created += month_stats['created']
            total_updated += month_stats['updated']
            total_skipped += month_stats['skipped']

        return {
            'processed': total_processed,
            'created': total_created,
            'updated': total_updated,
            'skipped': total_skipped
        }

    def process_specific_month(self, year, month, feeder_slug=None):
        """Process a specific year and month"""
        if year not in self.ENERGY_BILLED_DATA:
            raise CommandError(f"No energy billed data available for year {year}")

        monthly_data = self.ENERGY_BILLED_DATA[year]
        if month > len(monthly_data):
            raise CommandError(f"No data available for {year}-{month:02d}")

        # Get the energy billed for this month (convert GWh to MWh)
        energy_gwh = monthly_data[month - 1]
        disco_total_energy_billed_mwh = Decimal(str(energy_gwh * 1000))  # Convert GWh to MWh

        # Create the month date (first day of month)
        month_date = date(year, month, 1)
        month_start = month_date
        month_end = month_start + relativedelta(months=1)

        self.stdout.write(
            f"Processing {month_date.strftime('%B %Y')}: "
            f"{energy_gwh} GWh ({disco_total_energy_billed_mwh} MWh)"
        )

        # Get all feeders or specific feeder
        if feeder_slug:
            feeders = Feeder.objects.filter(slug=feeder_slug)
            if not feeders.exists():
                raise CommandError(f"Feeder with slug '{feeder_slug}' not found")
        else:
            feeders = Feeder.objects.all()

        # Calculate total energy delivered across all feeders for this month
        total_energy_delivered = EnergyDelivered.objects.filter(
            date__gte=month_start,
            date__lt=month_end
        ).aggregate(total=Sum('energy_mwh'))['total'] or Decimal('0')

        if total_energy_delivered == 0:
            self.stdout.write(
                self.style.WARNING(
                    f"No energy delivered data found for {month_date.strftime('%B %Y')}. "
                    f"Skipping this month."
                )
            )
            return {'processed': 0, 'created': 0, 'updated': 0, 'skipped': 1}

        self.stdout.write(f"Total energy delivered: {total_energy_delivered} MWh")

        # Process each feeder
        processed = 0
        created = 0
        updated = 0
        skipped = 0

        feeders_with_delivery = feeders.filter(
            energydelivered__date__gte=month_start,
            energydelivered__date__lt=month_end
        ).distinct()

        if not feeders_with_delivery.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"No feeders with energy delivery data found for {month_date.strftime('%B %Y')}"
                )
            )
            return {'processed': 0, 'created': 0, 'updated': 0, 'skipped': 1}

        progress_desc = f"Processing feeders for {month_date.strftime('%b %Y')}"
        
        for feeder in tqdm(feeders_with_delivery, desc=progress_desc, unit="feeder"):
            # Calculate feeder's energy delivered for this month
            feeder_energy_delivered = EnergyDelivered.objects.filter(
                feeder=feeder,
                date__gte=month_start,
                date__lt=month_end
            ).aggregate(total=Sum('energy_mwh'))['total'] or Decimal('0')

            if feeder_energy_delivered == 0:
                skipped += 1
                continue

            # Calculate proportional allocation
            # Feeder_Billed_Energy = (Feeder_Delivered / Total_Delivered) × DisCo_Total_Billed
            proportion = feeder_energy_delivered / total_energy_delivered
            feeder_billed_energy = (proportion * disco_total_energy_billed_mwh).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )

            if not self.dry_run:
                # Create or update the record
                monthly_billed, record_created = MonthlyEnergyBilled.objects.update_or_create(
                    feeder=feeder,
                    month=month_date,
                    defaults={'energy_mwh': feeder_billed_energy}
                )

                if record_created:
                    created += 1
                else:
                    if self.force:
                        updated += 1
                    else:
                        # Record exists and force not specified
                        skipped += 1
                        continue
            else:
                # Dry run - check if record exists
                exists = MonthlyEnergyBilled.objects.filter(
                    feeder=feeder,
                    month=month_date
                ).exists()
                
                if exists and not self.force:
                    skipped += 1
                elif exists:
                    updated += 1
                else:
                    created += 1

            processed += 1

            # Log detailed info for single feeder processing
            if feeder_slug:
                self.stdout.write(
                    f"  {feeder.name}: {feeder_energy_delivered} MWh delivered → "
                    f"{feeder_billed_energy} MWh billed "
                    f"({proportion:.4%} share)"
                )

        return {
            'processed': processed,
            'created': created,
            'updated': updated,
            'skipped': skipped
        }

    def print_summary(self, processed, created, updated, skipped):
        """Print processing summary"""
        self.stdout.write(f"\n{'='*60}")
        if self.dry_run:
            self.stdout.write(self.style.SUCCESS("DRY RUN SUMMARY"))
        else:
            self.stdout.write(self.style.SUCCESS("PROCESSING COMPLETE"))
        self.stdout.write(f"{'='*60}")
        self.stdout.write(self.style.SUCCESS(f"Records processed: {processed}"))
        self.stdout.write(self.style.SUCCESS(f"Records created: {created}"))
        if updated > 0:
            self.stdout.write(self.style.SUCCESS(f"Records updated: {updated}"))
        if skipped > 0:
            self.stdout.write(self.style.WARNING(f"Records skipped: {skipped}"))
        self.stdout.write(f"{'='*60}")

        if self.dry_run:
            self.stdout.write(
                self.style.HTTP_INFO(
                    "To execute these changes, run the command without --dry-run"
                )
            )
        elif skipped > 0 and not self.force:
            self.stdout.write(
                self.style.HTTP_INFO(
                    "To overwrite existing records, use the --force flag"
                )
            )