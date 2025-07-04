import uuid
from django.conf import settings
from django.shortcuts import render, redirect
from django.urls import reverse_lazy, reverse
from django.http import HttpResponseNotAllowed, HttpResponseBadRequest, HttpResponseNotFound, JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt # Temporarily for testing AJAX, remove in prod!
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.utils.translation import gettext as _ # Import gettext for runtime translation

from orders.models import Category, Order, OrderDetail, Feature, OrderFeatureDetail
from orders.utils import generate_download_url, get_r2_client

# Third Party
from datetime import datetime
from json import loads
import os
from urllib.parse import urlencode


# --- Helper ---
def get_order_for_processing(worker_id):
    with transaction.atomic():
        # Lock only one order that is still new
        order = (
            Order.objects
            .select_for_update(skip_locked=True)
            .filter(status='pending')
            .order_by('created_at')
            .first()
        )
        
        if order:
            order.worker_id = worker_id
            order.status = 'processing'
            order.save(update_fields=['status', 'worker_id'])
        return order
    return None

# Create your views here.
# Home Page
def index(request):
    # List all opening order
    today = timezone.make_aware(datetime.today(), timezone=timezone.get_current_timezone())
    # print(today.date())
    # Today - Pending ordered by time
    orders = Order.objects.filter(created_at__gte=today.date()).order_by("created_at")
    pending_orders = orders.filter(status="pending")
    processing_orders = orders.filter(status="processing")
    # print(len(processing_orders))
    return render(request, "orders/index.html", {
        "pending_orders" : pending_orders,
        "processing_orders" : processing_orders
    })


# Create Order
def create_order(request):
    if request.method == "POST":
        request_body = loads(request.body.decode("utf-8"))
        orders = request_body['orders']
        client = request_body['client']
        session_id = request_body['session']
        
        
        if not (orders and client and session_id):
            return HttpResponseBadRequest(_("All fields must be filled in"))
        
        order = Order(client=client, session_id=session_id)
        details = []
        details_features = []
        for order_data in orders:
            features_ids = order_data['features']
            quantity = order_data['quantity']
            file = order_data['file_url']
            note = order_data['note']
            features = []

            for feature_id in features_ids:
                try:
                    feature = Feature.objects.get(pk=feature_id)
                except:
                    return HttpResponseNotFound(_("Feature is not found!"))
                features.append(feature)
            
            # Features should be a list of corresponding features
            cost = float(sum([feature.price for feature in features]) * int(quantity))
            order_detail = OrderDetail(
                document=file,
                quantity=quantity,
                cost=round(cost, 2),
                order_id=order,
                note=note
            )
            details.append(order_detail)
            details_features.extend([
                OrderFeatureDetail(
                    order_detail_id=order_detail,
                    feature_id=feature
                )
                for feature in features
            ])
        order.total_cost = sum([order_detail.cost for order_detail in details])
        order.save()

        # TODO: Optimization here!
        # for d in details:
        #     d.order_id = order
        OrderDetail.objects.bulk_create(details)

        # for d in details_features:
        #     d.order_id = order.pk
        OrderFeatureDetail.objects.bulk_create(details_features)

        return JsonResponse({"message" : _("Order is placed successfully!")}, status=200)


    elif request.method == "GET":
        # Send Features with their prices
        categories = Category.objects.all()
        return render(request, "orders/create_orders.html", {
            "categories" : categories
        })

    return HttpResponseNotAllowed(['DELETE', 'PATCH', 'PUT'])

# Return presigned url for upload
@csrf_exempt # !!! REMOVE IN PRODUCTION !!!
def get_presigned_url(request):
    file_name = request.POST.get('fileName')
    file_type = request.POST.get('fileType') # e.g., 'image/jpeg', 'application/pdf'

    if not file_name or not file_type:
        return JsonResponse({'error': _('fileName and fileType are required')}, status=400)

    # Generate a unique key for the file in R2
    # It's good practice to add a UUID to prevent collisions and make guessing harder
    # You might also include user ID or a timestamp if relevant
    file, ext = os.path.splitext(file_name)
    r2_key = f"uploads/{file}-{uuid.uuid1()}{ext}" # Example path: uploads/unique-id.pdf

    try:
        s3_client = get_r2_client()
        presigned_post = s3_client.generate_presigned_url(
            'put_object',
            Params={'Bucket': settings.CLOUDFLARE_R2_BUCKET_NAME , 'Key': r2_key, 'ContentType': file_type},
            ExpiresIn=300, # URL valid for 5 minutes (in seconds)
            HttpMethod='PUT'
        )
        # presigned_post will contain 'url' and 'fields'
        # The 'url' is the R2 endpoint, 'fields' are the form data fields (like AWSAccessKeyId, signature, etc.)

        return JsonResponse({
            'presignedUrl': presigned_post,
            "r2Key" : r2_key,
        })
    except Exception as e:
        return JsonResponse({'error': _('Failed to generate presigned URL: %s') % str(e)}, status=500)

# Change Order Status
@csrf_exempt
def change_order_status(request):
    if request.method == "POST":
        order_data = loads(request.body.decode("utf-8"))
        order_id = order_data['order_id']
        status = order_data['status']

        # Get order by id + session_id + status pending
        order = Order.objects.filter(
            pk=order_id
        )
        if not request.user.is_authenticated:
            session_id = order_data['session_id']
            order = order.filter(session_id=session_id, status="pending")

        order = order.first()
        if order and (order.status == "pending" or request.user.is_authenticated): 
            print("Order is found!")
            order.status = status
            order.save()

            # print(order.status)
            return JsonResponse({
                "message" : _("Order is %s successfully") % status
            }, status=200)
    
        return JsonResponse({
            "message" : _("Bad request, status is not allowed!")
        }, status=400)
    
    return HttpResponseNotAllowed(['DELETE', 'GET', 'PATCH', 'PUT'])


# Accept Order
@csrf_exempt
def get_next_orders(request):
    # Ensure Authenticated
    if not request.user.is_authenticated:
        return HttpResponseForbidden(_("You are not authorized to login"))
    # GET Request => Render Page
    if request.method == "GET":
        accepted_orders = Order.objects.filter(status="accepted", worker_id=request.user)
        return render(request, "orders/orders_dashboard.html", {
            "accepted_orders" : accepted_orders
        })
    
    elif request.method == "POST":
        next_order = get_order_for_processing(request.user)
        if next_order:
           
            return JsonResponse({
                "message" : _("Order is successfully retrieved!"),
                "order" : next_order.serialize()
            }) 

        return JsonResponse({"message" : _("There are no orders for processing")}, status=200)

    else:
        return HttpResponseNotAllowed(['DELETE', "PUT", "PATCH"])


# Get Order by Id
@csrf_exempt
def get_order(request, order_id):
    if request.method == "POST":
        try:
            order = Order.objects.get(pk=order_id)
            return JsonResponse({
                "message" : _("Order is successfully retrieved!"),
                "order" : order.serialize()
            }) 
        except:
            return HttpResponseNotFound("Order is not found!")
    return HttpResponseNotAllowed(["GET", "PUT", "DELETE"])


# Report Page
def report_dashboard(request):
    # GET
    # ['accepted', 'finished', 'declined', 'pending', 'processing']
    if request.method == "GET":
        tables = [
            {
                "state" : state,
            }
            for state in ['finished', 'declined', 'processing']
        
        ]
            
        return render(request, "orders/report_dashboard.html", {
            "tables" : tables
        })
    
    return HttpResponseNotAllowed(["POST", "PATCH", "DELETE", "PUT"])


# Order Page
def order_table(request, state):
    if not request.user.is_authenticated:
        return HttpResponseForbidden("Not authorized!")
    if request.method == "GET":
        if state not in  ['accepted', 'declined', 'pending', 'processing', "finished"]:
            return HttpResponseBadRequest(_("Invalid state for orders!"))

        CLASSES = {
            'accepted' : 'bg-primary',
            'finished' : 'bg-success',
            'declined' : 'bg-danger',
            'processing' : 'bg-info',
            'pending' : 'bg-secondary',
        }

        search_query = request.GET.get("query", "") # String [Client_name]
        date_from = request.GET.get("from", "") # Date
        date_to = request.GET.get("to", "") # Date
        by_worker = request.GET.get("by", 0) # ID
        page = request.GET.get("page", 1)
        filters = {
            "status" : state
        }

        if search_query:
            filters['client__icontains'] = search_query

        if date_from:
            # TODO => Handle Date not matching
            date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            filters['created_at__gte'] = date_from
        else:
            today = timezone.make_aware(datetime.today(), timezone=timezone.get_current_timezone())
            filters['created_at__gte'] = today
            

        if date_to:
            date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
            filters['created_at__lte'] = date_to

        if by_worker:
            filters['worker_id'] = by_worker

        orders = Order.objects.filter(**filters).order_by("id")
        orders_page = Paginator(orders, settings.PAGE_SIZE)
        current_page = orders_page.get_page(page)

        has_previous = current_page.has_previous()
        has_next = current_page.has_next()

        base_url = reverse("order-table", args=[state,])
        query_params = request.GET.copy()
        query_params["page"] = page + 1
        next_url = f"{base_url}?{query_params.urlencode()}" if has_next else None
        query_params["page"] = page - 2
        prev_url = f"{base_url}?{query_params.urlencode()}" if has_previous else None

        orders = [order.serialize() for order in current_page.object_list]

        return render(request, "orders/orders_table.html", {
            "base_url" : base_url,
            "state_class" : CLASSES[state],
            "next_url" : next_url,
            "previous_url" : prev_url,
            "state" : state,
            "orders" : [order.serialize() for order in current_page.object_list],
            "num_pages" : current_page.paginator.num_pages,
            "has_previous" : has_previous,
            "has_next" : has_next,
            "number" : current_page.number,
            "to" : date_to,
            "from" : date_from,
            "query" : search_query,
            "workers" : User.objects.all()
        })
    
    return HttpResponseNotAllowed(["POST", "PATCH", "DELETE", "PUT"])

# Login Page
def display_login(request):
    if not request.user.is_authenticated:
        return render(request, "orders/login.html")
    return redirect(reverse_lazy("home"))