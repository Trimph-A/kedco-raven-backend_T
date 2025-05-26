from django.db.models import Sum
from commercial.models import DailyCollection
from technical.models import EnergyDelivered
from financial.models import MonthlyRevenueBilled
from django.utils.dateparse import parse_date
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal, InvalidOperation



def get_commercial_overview_data(mode, year, month, from_date, to_date):
    def generate_month_list(reference_date):
        return [reference_date - relativedelta(months=i) for i in range(4, -1, -1)]

    # Resolve current period
    if mode == "monthly":
        selected_date = date(year, month, 1)
    else:
        selected_date = parse_date(to_date) or date.today()

    months = generate_month_list(selected_date)

    def month_filter(month):
        return {
            "date__year": month.year,
            "date__month": month.month
        }

    data = {
        "energy_delivered": [],
        "billing_efficiency": [],
        "collection_efficiency": [],
        "atcc": [],
        "customer_response_rate": [],
        "revenue_billed_per_customer": [],
        "collections_per_customer": [],
        "customer_response_metric": []
    }

    for m in months:
        delivered = EnergyDelivered.objects.filter(**month_filter(m)).aggregate(Sum("energy_mwh"))["energy_mwh__sum"] or 0
        billed = MonthlyRevenueBilled.objects.filter(month__year=m.year, month__month=m.month).aggregate(Sum("amount"))["amount__sum"] or 0
        collected = DailyCollection.objects.filter(**month_filter(m)).aggregate(Sum("amount"))["amount__sum"] or 0

        
        billing_eff = round((billed / delivered * 100) if delivered else 0, 2)
        collection_eff = round((collected / billed * 100) if billed else 0, 2)
        atcc = round((collected / delivered * 100) if delivered else 0, 2)

        try:
            billing_eff = (Decimal(billed) / Decimal(delivered)) if delivered else Decimal(0)
            collection_eff = (Decimal(collected) / Decimal(billed)) if billed else Decimal(0)
            atcc = round((billing_eff * collection_eff * Decimal('100')), 2)

            billing_eff = round(billing_eff * Decimal('100'), 2)
            collection_eff = round(collection_eff * Decimal('100'), 2)

        except (InvalidOperation, ZeroDivisionError):
            billing_eff = collection_eff = atcc = Decimal(0)

        

        data["energy_delivered"].append({"month": m.strftime("%b"), "value": float(delivered)})
        data["billing_efficiency"].append({"month": m.strftime("%b"), "value": float(billing_eff)})
        data["collection_efficiency"].append({"month": m.strftime("%b"), "value": float(collection_eff)})
        data["atcc"].append({"month": m.strftime("%b"), "value": float(atcc)})


    return data
