from django.contrib import admin
from orders.models import *
# Register your models here.

admin.site.register(Order)
admin.site.register(Category)
admin.site.register(Feature)
admin.site.register(OrderDetail)
admin.site.register(OrderFeatureDetail)
