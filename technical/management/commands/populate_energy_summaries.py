# backend/technical/management/commands/populate_energy_summaries.py

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.db import transaction
from django.db.models.functions import ExtractYear, ExtractMonth
from django.utils import timezone
from datetime import timedelta, date

from technical.models import (
    EnergyDelivered,
    FeederEnergyDaily,
    FeederEnergyMonthly,
)

class Command(BaseCommand):
    help = (
        "Populate FeederEnergyDaily and FeederEnergyMonthly summaries.\n"
        "By default runs incrementally (yesterday + last month).\n"
        "Use --daily-only or --monthly-only to restrict.\n"
        "Use --full to drop & rebuild all summaries."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--daily-only",
            action="store_true",
            help="Only (re)compute daily summaries."
        )
        parser.add_argument(
            "--monthly-only",
            action="store_true",
            help="Only (re)compute monthly summaries."
        )
        parser.add_argument(
            "--full",
            action="store_true",
            help="Wipe and rebuild ALL daily & monthly summaries from scratch."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        full = options["full"]
        do_daily = not options["monthly_only"]
        do_monthly = not options["daily_only"]

        if full:
            self.stdout.write(self.style.WARNING("⚠ FULL RECOMPUTE: clearing summaries…"))
            FeederEnergyDaily.objects.all().delete()
            FeederEnergyMonthly.objects.all().delete()

        # DAILY
        if do_daily:
            if full:
                # full: aggregate every date in the facts table
                daily_qs = (
                    EnergyDelivered.objects
                    .values("feeder_id", "date")
                    .annotate(total_mwh=Sum("energy_mwh"))
                )
                self.stdout.write("▶ FULL daily aggregation (all dates)…")
            else:
                # incremental: only yesterday
                yesterday = timezone.localdate() - timedelta(days=1)
                daily_qs = (
                    EnergyDelivered.objects
                    .filter(date=yesterday)
                    .values("feeder_id", "date")
                    .annotate(total_mwh=Sum("energy_mwh"))
                )
                self.stdout.write(f"▶ Incremental daily: {yesterday}")

            for row in daily_qs:
                FeederEnergyDaily.objects.update_or_create(
                    feeder_id=row["feeder_id"],
                    date=row["date"],
                    defaults={"energy_mwh": row["total_mwh"]},
                )
            self.stdout.write(f"  • Daily rows processed: {daily_qs.count()}")

        # MONTHLY
        if do_monthly:
            if full:
                # full: build from all daily summaries
                src = FeederEnergyDaily.objects
                self.stdout.write("▶ FULL monthly aggregation (all months)…")
            else:
                # incremental: just the last calendar month’s days
                today = timezone.localdate()
                first_of_this_month = today.replace(day=1)
                last_month_end = first_of_this_month - timedelta(days=1)
                last_month_start = last_month_end.replace(day=1)
                src = FeederEnergyDaily.objects.filter(
                    date__gte=last_month_start,
                    date__lte=last_month_end
                )
                self.stdout.write(f"▶ Incremental monthly: {last_month_start:%Y-%m}")

            monthly_qs = (
                src
                .annotate(
                    year=ExtractYear("date"),
                    month=ExtractMonth("date")
                )
                .values("feeder_id", "year", "month")
                .annotate(total_mwh=Sum("energy_mwh"))
            )

            created = 0
            for row in monthly_qs:
                period = date(year=row["year"], month=row["month"], day=1)
                FeederEnergyMonthly.objects.update_or_create(
                    feeder_id=row["feeder_id"],
                    period=period,
                    defaults={"energy_mwh": row["total_mwh"]},
                )
                created += 1

            self.stdout.write(f"  • Monthly rows processed: {monthly_qs.count()}")

        self.stdout.write(self.style.SUCCESS("✔ Summaries populated."))
