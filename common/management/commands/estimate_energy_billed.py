from django.core.management.base import BaseCommand
from datetime import datetime
from dateutil.relativedelta import relativedelta  # type: ignore
from decimal import Decimal
from common.models import Feeder
from commercial.models import MonthlyEnergyBilled

# Dummy data in GWh — one value per month
ENERGY_BILLED_DATA = {
    2022: [Decimal(v) for v in [140.9, 126.0, 105.0, 109.0, 96.0, 86.0, 101.0, 116.0, 104.0, 112.0, 125.8, 124.1]],
    2023: [Decimal(v) for v in [118.7, 114.4, 134.9, 103.7, 104.4, 95.9, 95.6, 97.5, 99.2, 109.0, 124.6, 128.3]],
    2024: [Decimal(v) for v in [116.0, 102.8, 111.1, 103.4, 122.0, 106.2, 136.9, 137.8, 141.2, 85.0, 80.3, 109.2]],
    2025: [Decimal(v) for v in [99.9, 104.0, 140.8]],
}


class Command(BaseCommand):
    help = 'Populate MonthlyEnergyBilled by feeder from dummy data (in GWh), converting to MWh.'

    def handle(self, *args, **options):
        feeders = Feeder.objects.all()
        start_date = datetime(2022, 1, 1)
        end_date = datetime(2025, 12, 1)

        current_date = start_date
        while current_date <= end_date:
            year = current_date.year
            month_index = current_date.month - 1

            if year not in ENERGY_BILLED_DATA:
                self.stdout.write(self.style.WARNING(f"Skipping {year}: No data provided."))
                current_date += relativedelta(months=1)
                continue

            if month_index >= len(ENERGY_BILLED_DATA[year]):
                self.stdout.write(self.style.WARNING(f"Skipping {year}-{current_date.month:02d}: No monthly value."))
                current_date += relativedelta(months=1)
                continue

            # Convert from GWh to MWh
            energy_mwh = ENERGY_BILLED_DATA[year][month_index] * Decimal(1000)

            for feeder in feeders:
                MonthlyEnergyBilled.objects.update_or_create(
                    feeder=feeder,
                    month=current_date,
                    defaults={'energy_mwh': round(energy_mwh, 2)}
                )
                self.stdout.write(self.style.SUCCESS(
                    f"{feeder.name} | {current_date.strftime('%b %Y')} → {round(energy_mwh, 2)} MWh"
                ))

            current_date += relativedelta(months=1)
