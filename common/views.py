from rest_framework import viewsets
from .models import *
from .serializers import *

class StateViewSet(viewsets.ModelViewSet):
    queryset = State.objects.all()
    serializer_class = StateSerializer

class BusinessDistrictViewSet(viewsets.ModelViewSet):
    queryset = BusinessDistrict.objects.all()
    serializer_class = BusinessDistrictSerializer

class InjectionSubstationViewSet(viewsets.ModelViewSet):
    queryset = InjectionSubstation.objects.all()
    serializer_class = InjectionSubstationSerializer

class FeederViewSet(viewsets.ModelViewSet):
    queryset = Feeder.objects.all()
    serializer_class = FeederSerializer

class DistributionTransformerViewSet(viewsets.ModelViewSet):
    queryset = DistributionTransformer.objects.all()
    serializer_class = DistributionTransformerSerializer

class BandViewSet(viewsets.ModelViewSet):
    queryset = Band.objects.all()
    serializer_class = BandSerializer
