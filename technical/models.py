from django.db import models
from common.models import Feeder
from django.utils import timezone


class EnergyDelivered(models.Model):
    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE)
    date = models.DateField()
    energy_mwh = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('feeder', 'date')


class HourlyLoad(models.Model):
    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE)
    date = models.DateField()
    hour = models.PositiveSmallIntegerField()  # 0 to 23
    load_mw = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('feeder', 'date', 'hour')


class FeederInterruption(models.Model):
    INTERRUPTION_TYPES = [
        ('load_shedding', 'Load Shedding'),
        ('fault', 'Fault'),
        ('permit', 'Permit'),
        # Add more types per DisCo
    ]
    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE)
    interruption_type = models.CharField(max_length=50, choices=INTERRUPTION_TYPES)
    occurred_at = models.DateTimeField()
    restored_at = models.DateTimeField()

    @property
    def duration_hours(self):
        return (self.restored_at - self.occurred_at).total_seconds() / 3600


class DailyHoursOfSupply(models.Model):
    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE)
    date = models.DateField()
    hours_supplied = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        unique_together = ('feeder', 'date')
