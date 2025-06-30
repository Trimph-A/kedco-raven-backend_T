from datetime import date, datetime
from dateutil.relativedelta import relativedelta  # type: ignore
from django.db.models import Sum
from django.utils.dateparse import parse_date
from decimal import Decimal, InvalidOperation

from commercial.models import MonthlyCommercialSummary, MonthlyEnergyBilled
from technical.models import EnergyDelivered


def get_commercial_overview_data(mode, year, month, from_date, to_date):
    def generate_month_list(reference_date):
        return [reference_date - relativedelta(months=i) for i in range(4, -1, -1)]

    if mode == "monthly":
        selected_date = date(year, month, 1)
    else:
        selected_date = parse_date(to_date) or date.today()

    months = generate_month_list(selected_date)

    data = {
        "energy_delivered": [],
        "energy_billed": [],
        "energy_collected": [],
        "billing_efficiency": [],
        "collection_efficiency": [],
        "atcc": [],
        "customer_response_rate": [],
        "revenue_billed_per_customer": [],
        "collections_per_customer": [],
        "customer_response_metric": []
    }

    def append_with_delta(metric_list, value, label):
        value = Decimal(value)
        last_value = Decimal(str(metric_list[-1]["value"])) if metric_list else None

        if last_value and last_value != 0:
            delta = round(((value - last_value) / last_value) * Decimal("100"), 2)
        else:
            delta = None

        metric_list.append({
            "month": label,
            "value": float(value),
            "delta": float(delta) if delta is not None else None
        })

    for m in months:
        label = m.strftime("%b")

        summary = MonthlyCommercialSummary.objects.filter(month=m).aggregate(
            revenue_billed=Sum("revenue_billed"),
            revenue_collected=Sum("revenue_collected"),
            customers_billed=Sum("customers_billed"),
            customers_responded=Sum("customers_responded"),
        )
        energy_billed = MonthlyEnergyBilled.objects.filter(month=m).aggregate(
            energy=Sum("energy_mwh")
        )["energy"] or 0
        energy_delivered = EnergyDelivered.objects.filter(
            date__year=m.year, date__month=m.month
        ).aggregate(Sum("energy_mwh"))["energy_mwh__sum"] or 0

        revenue_billed = summary["revenue_billed"] or 0
        revenue_collected = summary["revenue_collected"] or 0
        customers_billed = summary["customers_billed"] or 0
        customers_responded = summary["customers_responded"] or 0

        try:
            billing_eff = Decimal(energy_billed) / Decimal(energy_delivered) if energy_delivered else Decimal(0)
            collection_eff = Decimal(revenue_collected) / Decimal(revenue_billed) if revenue_billed else Decimal(0)
            atcc = Decimal(1) - (billing_eff * collection_eff)

            billing_eff_pct = round(billing_eff * Decimal("100"), 2)
            collection_eff_pct = round(collection_eff * Decimal("100"), 2)
            atcc_pct = round(atcc * Decimal("100"), 2)

            revenue_billed_pc = round(Decimal(revenue_billed) / Decimal(customers_billed), 2) if customers_billed else Decimal(0)
            collections_pc = round(Decimal(revenue_collected) / Decimal(customers_billed), 2) if customers_billed else Decimal(0)
            response_rate = round(Decimal(customers_responded) / Decimal(customers_billed) * Decimal("100"), 2) if customers_billed else Decimal(0)

            # Updated customer response metric calculation
            response_metric = (
                round(collections_pc / revenue_billed_pc, 2)
                if revenue_billed_pc != 0
                else Decimal(0)
            )

        except (InvalidOperation, ZeroDivisionError):
            billing_eff_pct = collection_eff_pct = atcc_pct = Decimal(0)
            revenue_billed_pc = collections_pc = response_rate = response_metric = Decimal(0)

        append_with_delta(data["energy_delivered"], energy_delivered, label)
        append_with_delta(data["energy_billed"], energy_billed, label)
        append_with_delta(data["energy_collected"], revenue_collected, label)

        data["billing_efficiency"].append({"month": label, "value": float(billing_eff_pct)})
        data["collection_efficiency"].append({"month": label, "value": float(collection_eff_pct)})
        data["atcc"].append({"month": label, "value": float(atcc_pct)})

        append_with_delta(data["customer_response_rate"], response_rate, label)
        append_with_delta(data["revenue_billed_per_customer"], revenue_billed_pc, label)
        append_with_delta(data["collections_per_customer"], collections_pc, label)
        append_with_delta(data["customer_response_metric"], response_metric, label)

    return data
