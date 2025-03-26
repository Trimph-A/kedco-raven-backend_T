from django.db import models
from uuid import uuid4

class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)

    class Meta:
        abstract = True


class State(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class BusinessDistrict(models.Model):
    name = models.CharField(max_length=100)
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name='districts')

    class Meta:
        unique_together = ('name', 'state')

    def __str__(self):
        return f"{self.name} ({self.state.name})"


class InjectionSubstation(models.Model):
    name = models.CharField(max_length=100)
    district = models.ForeignKey(BusinessDistrict, on_delete=models.CASCADE, related_name='substations')

    class Meta:
        unique_together = ('name', 'district')

    def __str__(self):
        return f"{self.name} - {self.district}"


class Feeder(models.Model):
    name = models.CharField(max_length=100)
    substation = models.ForeignKey(InjectionSubstation, on_delete=models.CASCADE, related_name='feeders')

    class Meta:
        unique_together = ('name', 'substation')

    def __str__(self):
        return f"{self.name} - {self.substation}"


class DistributionTransformer(models.Model):
    name = models.CharField(max_length=100)
    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE, related_name='transformers')

    class Meta:
        unique_together = ('name', 'feeder')

    def __str__(self):
        return f"{self.name} - {self.feeder}"


# Optional: Prepare for banding
class Band(models.Model):
    name = models.CharField(max_length=50, unique=True)  # e.g., Band A, Band B
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name
