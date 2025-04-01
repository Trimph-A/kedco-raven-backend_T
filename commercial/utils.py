from common.models import Feeder
from commercial.models import Customer

def get_filtered_feeders(request):
    filters = {}
    state_slug = request.GET.get('state')
    district_slug = request.GET.get('district')
    substation_slug = request.GET.get('substation')
    transformer_slug = request.GET.get('transformer')
    feeder_slug = request.GET.get('feeder')
    band_slug = request.GET.get('band')

    if feeder_slug:
        filters['slug'] = feeder_slug
    elif transformer_slug:
        filters['transformers__slug'] = transformer_slug
    elif substation_slug:
        filters['substation__slug'] = substation_slug
    elif district_slug:
        filters['substation__district__slug'] = district_slug
    elif state_slug:
        filters['substation__district__state__slug'] = state_slug

    feeders = Feeder.objects.filter(**filters).distinct()

    if band_slug:
        feeders = feeders.filter(
            transformers__customer__band__slug=band_slug
        ).distinct()

    return feeders


def get_filtered_customers(request):
    customers = Customer.objects.all()

    # Location filters
    state = request.GET.get('state')
    district = request.GET.get('district')
    substation = request.GET.get('substation')
    feeder = request.GET.get('feeder')
    transformer = request.GET.get('transformer')
    band = request.GET.get('band')

    if transformer:
        customers = customers.filter(transformer__slug=transformer)
    elif feeder:
        customers = customers.filter(transformer__feeder__slug=feeder)
    elif substation:
        customers = customers.filter(transformer__feeder__substation__slug=substation)
    elif district:
        customers = customers.filter(transformer__feeder__substation__district__slug=district)
    elif state:
        customers = customers.filter(transformer__feeder__substation__district__state__slug=state)

    if band:
        customers = customers.filter(band__slug=band)

    # Other filters
    category = request.GET.get('category')
    if category:
        customers = customers.filter(category=category)

    metering_type = request.GET.get('metering_type')
    if metering_type:
        customers = customers.filter(metering_type=metering_type)

    # Date filtering
    joined_date = request.GET.get('joined_date')
    joined_from = request.GET.get('joined_from')
    joined_to = request.GET.get('joined_to')

    if joined_date:
        customers = customers.filter(joined_date=joined_date)
    elif joined_from and joined_to:
        customers = customers.filter(joined_date__range=(joined_from, joined_to))
    elif joined_from:
        customers = customers.filter(joined_date__gte=joined_from)
    elif joined_to:
        customers = customers.filter(joined_date__lte=joined_to)

    return customers
