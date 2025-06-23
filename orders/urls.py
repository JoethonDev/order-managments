from django.urls import path
from orders.views import *

urlpatterns = [
    path('', index, name="home"),
    path('login', display_login, name="display-login"),
    path('orders', create_order, name="create-order"),
    path('orders/change', change_order_status, name="change-order"),
    path('orders/next', get_next_orders, name="order-dashboard"),
    path('reports/<str:state>', order_table, name="order-table"),
    path('reports/', report_dashboard, name="report-dashboard"),
    path('api/get-presigned-url/', get_presigned_url, name="presigned-upload"),
]