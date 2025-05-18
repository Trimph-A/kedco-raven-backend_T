class LocationFilterMixin:
    """
    Adds filtering by:
    - state
    - district
    - substation
    - feeder
    - transformer
    Works with models connected via ForeignKey chains.
    """
    def filter_by_location(self, qs):
        request = self.request
        state = request.GET.get("state")
        district = request.GET.get("district")
        substation = request.GET.get("substation")
        feeder = request.GET.get("feeder")
        transformer = request.GET.get("transformer")

        if transformer:
            qs = qs.filter(transformer__slug=transformer)
        elif feeder:
            qs = qs.filter(feeder__slug=feeder)
        elif substation:
            qs = qs.filter(feeder__substation__slug=substation)
        elif district:
            qs = qs.filter(feeder__substation__district__slug=district)
        elif state:
            qs = qs.filter(feeder__substation__district__state__slug=state)

        return qs


class DistrictLocationFilterMixin:
    def filter_by_location(self, qs):
        request = self.request
        state = request.GET.get("state")
        district = request.GET.get("district")

        if district:
            qs = qs.filter(district__slug=district)
        elif state:
            qs = qs.filter(district__state__slug=state)

        return qs
