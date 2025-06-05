from django.core.management.base import BaseCommand
from django.db.models import Sum
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta # type: ignore
from technical.models import EnergyDelivered
from commercial.models import MonthlyEnergyBilled
from common.models import Feeder
from decimal import Decimal

# Hardcoded billing efficiency estimates by (year, month)
ESTIMATED_BILLING_EFFICIENCY = {
    (2022, m): Decimal('0.484') for m in range(1, 13)
}
ESTIMATED_BILLING_EFFICIENCY.update({
    (2023, m): Decimal('0.55') for m in range(1, 13)
})
ESTIMATED_BILLING_EFFICIENCY.update({
    (2024, m): Decimal(str(v)) / 100 for m, v in enumerate(
        [51, 53, 55, 57, 59, 61, 63, 65, 67, 69, 71, 73], start=1
    )
})
ESTIMATED_BILLING_EFFICIENCY.update({
    (2025, m): Decimal(str(v)) / 100 for m, v in enumerate(
        [75, 77, 79, 81, 83, 85, 87, 89, 91, 93, 95, 97], start=1
    )
})


class Command(BaseCommand):
    help = 'Estimate and populate MonthlyEnergyBilled using energy delivered and billing efficiency estimates.'

    def handle(self, *args, **options):
        feeders = Feeder.objects.all()
        start_date = datetime(2022, 1, 1)
        end_date = datetime(2025, 12, 31)

        current_date = start_date
        while current_date <= end_date:
            month_start = datetime(current_date.year, current_date.month, 1)
            month_end = (month_start + relativedelta(months=1)) - timedelta(days=1)

            efficiency = ESTIMATED_BILLING_EFFICIENCY.get((current_date.year, current_date.month))
            if not efficiency:
                self.stdout.write(self.style.WARNING(f"No efficiency data for {current_date.year}-{current_date.month}, skipping..."))
                current_date += relativedelta(months=1)
                continue

            for feeder in feeders:
                delivered_sum = EnergyDelivered.objects.filter(
                    feeder=feeder,
                    date__range=(month_start, month_end)
                ).aggregate(total=Sum('energy_mwh'))['total'] or 0

                if delivered_sum <= 0:
                    continue  # skip if no energy delivered

                estimated_billed = Decimal(delivered_sum) * efficiency

                MonthlyEnergyBilled.objects.update_or_create(
                    feeder=feeder,
                    month=month_start,
                    defaults={'energy_mwh': round(estimated_billed, 2)}
                )
                self.stdout.write(self.style.SUCCESS(
                    f"Updated {feeder.name} for {month_start.strftime('%B %Y')}: {round(estimated_billed, 2)} MWh"
                ))

            current_date += relativedelta(months=1)
