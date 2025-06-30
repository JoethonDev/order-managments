from django.db import models
from django.contrib.auth.models import User

from orders.utils import generate_download_url

# Create your models here.
class Category(models.Model):
    category_name = models.CharField(max_length=255, null=False)

class Feature(models.Model):
    feature_name = models.CharField(max_length=255, null=False)
    price = models.FloatField()
    category_id = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="features", null=False)
    

class Order(models.Model):
    STATUS = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("cancelled", "Cancelled"),
        ("accepted", "Accepted"),
        ("finished", "Finished"),
        ("declined", "Declined")
    ]

    client = models.CharField(max_length=50)
    session_id = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    total_cost = models.FloatField()
    created_at = models.DateTimeField(auto_created=True, auto_now_add=True)
    worker_id = models.ForeignKey(User, on_delete=models.CASCADE, related_name="served_orders", null=True, default=None)


    def build_details(self):
        details = []
        for detail in self.details.all():
            features_ids = [feature_detail.feature_id.pk for feature_detail in detail.features.all()]
            features = [feature.feature_name for feature in Feature.objects.filter(pk__in=features_ids)]
            file_key = detail.document
            presigned_get = generate_download_url(file_key)

            file_name = file_key.split("/", 1)[1]
            details.append({
                "file_name" : file_name,
                "file_url" : presigned_get,
                "quantity" : detail.quantity,
                "cost" : detail.cost,
                "features" : features,
                "note" : detail.note,
            })
        return details
    
    def serialize(self):
        return {
            "id" : self.pk,
            "client" : self.client,
            "total_cost" : self.total_cost,
            "created_at" : self.created_at,
            "details" : self.build_details(),
        }

class OrderDetail(models.Model):
    document = models.CharField(max_length=255, null=False)
    quantity = models.IntegerField(default=1)
    cost = models.FloatField()
    order_id = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="details")
    note = models.TextField(null=True)


class OrderFeatureDetail(models.Model):
    order_detail_id = models.ForeignKey(OrderDetail, on_delete=models.CASCADE, related_name="features")
    feature_id = models.ForeignKey(Feature, on_delete=models.DO_NOTHING)