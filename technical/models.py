from django.db import models
from common.models import UUIDModel, Feeder
from django.utils import timezone


class EnergyDelivered(UUIDModel, models.Model):
    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE)
    date = models.DateField()
    energy_mwh = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('feeder', 'date')


class HourlyLoad(UUIDModel, models.Model):
    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE)
    date = models.DateField()
    hour = models.PositiveSmallIntegerField()  # 0 to 23
    load_mw = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('feeder', 'date', 'hour')


class FeederInterruption(UUIDModel, models.Model):
    INTERRUPTION_TYPES = [
        ("E/F", "Earth Fault"),
        ("O/C", "Overcurrent"),
        ("O/C & E/F", "Overcurrent and Earth Fault"),
        ("NO RI", "No RI"),
        ("N/A", "Not Specified"),
    ]
    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE)
    interruption_type = models.CharField(max_length=50, choices=INTERRUPTION_TYPES)
    description = models.TextField(blank=True, null=True)
    occurred_at = models.DateTimeField()
    restored_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ("feeder", "occurred_at", "interruption_type")

    @property
    def duration_hours(self):
        return (self.restored_at - self.occurred_at).total_seconds() / 3600


class DailyHoursOfSupply(UUIDModel, models.Model):
    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE)
    date = models.DateField()
    hours_supplied = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        unique_together = ('feeder', 'date')
