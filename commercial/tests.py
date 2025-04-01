import pytest
from datetime import date
from common.models import *
from commercial.models import *

@pytest.mark.django_db
def test_collection_efficiency():
    state = State.objects.create(name="Lagos")
    district = BusinessDistrict.objects.create(name="Ikeja", state=state)
    substation = InjectionSubstation.objects.create(name="SS", district=district)
    feeder = Feeder.objects.create(name="F1", substation=substation)

    MonthlyRevenueBilled.objects.create(feeder=feeder, month=date(2025, 3, 1), amount=100000)
    DailyRevenueCollected.objects.create(feeder=feeder, date=date(2025, 3, 5), amount=80000)

    billed = MonthlyRevenueBilled.objects.filter(feeder=feeder).aggregate(Sum('amount'))['amount__sum']
    collected = DailyRevenueCollected.objects.filter(feeder=feeder).aggregate(Sum('amount'))['amount__sum']
    efficiency = (collected / billed) * 100 if billed else 0

    assert billed == 100000
    assert collected == 80000
    assert round(efficiency, 2) == 80.00
