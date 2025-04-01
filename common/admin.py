from django.contrib import admin
from .models import (State,
                     BusinessDistrict,
                     InjectionSubstation,
                     Feeder,
                     DistributionTransformer,
                     Band)

@admin.register(State)
class PostAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    search_fields = ['name',]

@admin.register(BusinessDistrict)
class PostAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'state', ]
    list_filter = ['state',]
    search_fields = ['name',]

@admin.register(InjectionSubstation)
class PostAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'district',]
    list_filter = ['district',]
    search_fields = ['name',]

@admin.register(Feeder)
class PostAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'substation',]
    list_filter = ['substation',]
    search_fields = ['name',]

@admin.register(DistributionTransformer)
class PostAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'feeder',]
    list_filter = ['feeder',]
    search_fields = ['name',]

@admin.register(Band)
class PostAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    search_fields = ['name',]