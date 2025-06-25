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
    ("L/S", "Load Shedding (L/S)"),
    ("O/S", "Overload/Overcurrent (O/S)"),
    ("T/F", "Transformer Fault (T/F)"),
    ("B/F", "Bus/Breakdown Fault (B/F)"),
    ("O/N", "Overheating/Overtemp (O/N)"),
    ("O/E", "Open Earth (O/E)"),
    ("P/O", "Phase Open (P/O)"),
    ("O/F", "Over Frequency (O/F)"),
    ("P/M", "Phase Missing/Phase Metering (P/M)"),
    ("O", "Other Faults/Operational Fault (O)"),
    ("T/S", "Trip/Surge Fault (T/S)"),
    ("L/S GS", "Load Shedding – General Supply (L/S GS)"),
    ("MTNC", "Maintenance (MTNC)"),
    ("OC & E/F", "Open Circuit & Earth Fault (OC & E/F)"),
    ("EM/D", "Emergency/Device (EM/D)"),
    ("330KV L/F", "330 kV Line Fault (330KV L/F)"),
    ("OFF", "Switch Off/Feeder Off (OFF)"),
    ("S/C", "Short Circuit (S/C)"),
    ("132KV E/F", "132 kV Earth Fault (132KV E/F)"),
    ("132KV L/F", "132 kV Line Fault (132KV L/F)"),
    ("330KV L/S", "330 kV Line Shelving/Load Shedding (330KV L/S)"),
    ("132KV CB/F", "132 kV Circuit Breaker Failure (132KV CB/F)"),
    ("D/C", "Double Circuit/Direct Current (D/C)"),
    ("MTCE", "Maintenance (MTCE)"),
    ("IN O/C", "Incoming Over Current/Infeeder OC (IN O/C)"),
    ("T/LS", "Thermal Load Shedding (T/LS)"),
    ("132KV MTCE", "132 kV Maintenance (132KV MTCE)"),
    ("LIM", "Lightning Impulse/Limit (LIM)"),
    ("tcn", "(tcn)"),
    ("fault", "Fault"),
    ("permit", "Permit"),
]

    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE)
    interruption_type = models.CharField(max_length=100, choices=INTERRUPTION_TYPES)
    description = models.TextField(blank=True, null=True)
    occurred_at = models.DateTimeField()
    restored_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ("feeder", "occurred_at", "interruption_type")

    @property
    def duration_hours(self):
        if self.restored_at and self.occurred_at:
            return (self.restored_at - self.occurred_at).total_seconds() / 3600
        return 0


class DailyHoursOfSupply(UUIDModel, models.Model):
    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE)
    date = models.DateField()
    hours_supplied = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        unique_together = ('feeder', 'date')
