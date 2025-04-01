from django.db import models
from common.models import DistributionTransformer, Band
from django.utils import timezone

class Customer(models.Model):
    METERING_TYPE_CHOICES = [
        ('MD1', 'MD1'),
        ('MD2', 'MD2'),
        ('Non-MD', 'Non-MD'),
    ]

    CATEGORY_CHOICES = [
        ('Prepaid', 'Prepaid'),
        ('Postpaid', 'Postpaid'),
        ('Unmetered', 'Unmetered'),
    ]

    name = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    metering_type = models.CharField(max_length=20, choices=METERING_TYPE_CHOICES)
    band = models.ForeignKey(Band, on_delete=models.SET_NULL, null=True, blank=True)
    transformer = models.ForeignKey(DistributionTransformer, on_delete=models.PROTECT)

    joined_date = models.DateField(default=timezone.now)

    def __str__(self):
        return self.name


class DailyEnergyDelivered(models.Model):
    feeder = models.ForeignKey('common.Feeder', on_delete=models.CASCADE)
    date = models.DateField()
    energy_mwh = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('feeder', 'date')


class DailyRevenueCollected(models.Model):
    feeder = models.ForeignKey('common.Feeder', on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = ('feeder', 'date')


class MonthlyRevenueBilled(models.Model):
    feeder = models.ForeignKey('common.Feeder', on_delete=models.CASCADE)
    month = models.DateField()  # Always use first day of month (e.g., 2025-03-01)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = ('feeder', 'month')


class MonthlyEnergyBilled(models.Model):
    feeder = models.ForeignKey('common.Feeder', on_delete=models.CASCADE)
    month = models.DateField()
    energy_mwh = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('feeder', 'month')


class MonthlyCustomerStats(models.Model):
    feeder = models.ForeignKey('common.Feeder', on_delete=models.CASCADE)
    month = models.DateField()
    customer_count = models.PositiveIntegerField()
    customers_billed = models.PositiveIntegerField()
    customer_response_count = models.PositiveIntegerField()

    class Meta:
        unique_together = ('feeder', 'month')
