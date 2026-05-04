import json
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.templatetags.static import static
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import AuthToken, Category, CustomerProfile, DeliveryProfile, Order, OrderItem, Product, Store

SERVICE_CITY = "Ludhiana"


def body_json(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


def ok(payload=None, status=200):
    data = {"ok": True}
    if payload:
        data.update(payload)
    return JsonResponse(data, status=status)


def decimal_value(value, default="0"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def token_user(request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.removeprefix("Bearer ").strip()
    record = AuthToken.objects.select_related("user").filter(token=token).first()
    return record.user if record else None


def api_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = token_user(request)
        if not user:
            return error("Authentication required.", status=401)
        request.api_user = user
        return view_func(request, *args, **kwargs)

    return wrapper


def seller_required(view_func):
    @wraps(view_func)
    @api_login_required
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.api_user, "store"):
            return error("Seller account required.", status=403)
        return view_func(request, *args, **kwargs)

    return wrapper


def delivery_required(view_func):
    @wraps(view_func)
    @api_login_required
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.api_user, "delivery_profile"):
            return error("Delivery partner account required.", status=403)
        return view_func(request, *args, **kwargs)

    return wrapper


def unique_slug(model, value, current_id=None):
    base = slugify(value) or "item"
    slug = base
    counter = 2
    qs = model.objects.all()
    if current_id:
        qs = qs.exclude(id=current_id)
    while qs.filter(slug=slug).exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def role_for(user):
    if hasattr(user, "store"):
        return "seller"
    if hasattr(user, "delivery_profile"):
        return "delivery"
    return "customer"


def user_payload(user, request=None):
    payload = {
        "id": user.id,
        "username": user.username,
        "name": user.get_full_name() or user.username,
        "email": user.email,
        "role": role_for(user),
    }
    if hasattr(user, "customer_profile"):
        payload["phone"] = user.customer_profile.phone
        payload["address"] = user.customer_profile.address
    if hasattr(user, "delivery_profile"):
        payload["phone"] = user.delivery_profile.phone
        payload["city"] = user.delivery_profile.city
        payload["vehicle_type"] = user.delivery_profile.vehicle_type
        payload["status"] = user.delivery_profile.status
    if hasattr(user, "store"):
        payload["store"] = store_payload(user.store, request)
    return payload


def image_url(path, request):
    return request.build_absolute_uri(static(path))


def category_payload(category):
    return {
        "id": category.id,
        "name": category.name,
        "slug": category.slug,
        "icon": category.icon,
        "color": category.color,
    }


def store_payload(store, request):
    return {
        "id": store.id,
        "name": store.name,
        "slug": store.slug,
        "tagline": store.tagline,
        "description": store.description,
        "phone": store.phone,
        "email": store.email,
        "city": store.city,
        "address": store.address,
        "latitude": float(store.latitude) if store.latitude is not None else None,
        "longitude": float(store.longitude) if store.longitude is not None else None,
        "maps_url": store.maps_url,
        "opening_hours": store.opening_hours,
        "rating": float(store.rating),
        "delivery_window": store.delivery_window,
        "delivery_fee": float(store.delivery_fee),
        "cover_image": image_url(store.cover_image, request),
        "logo_image": image_url(store.logo_image, request),
        "is_open": store.is_open,
    }


def product_payload(product, request):
    return {
        "id": product.id,
        "store": store_payload(product.store, request),
        "category": category_payload(product.category) if product.category else None,
        "name": product.name,
        "slug": product.slug,
        "description": product.description,
        "price": float(product.price),
        "image": image_url(product.image, request),
        "stock": product.stock,
        "active": product.active,
        "featured": product.featured,
    }


def order_payload(order, request):
    return {
        "id": order.id,
        "order_id": order.order_id,
        "customer": order.customer.get_full_name() or order.customer.username,
        "store": store_payload(order.store, request),
        "delivery_partner": order.delivery_partner.get_full_name() if order.delivery_partner else None,
        "status": order.status,
        "status_label": order.get_status_display(),
        "delivery_address": order.delivery_address,
        "payment_method": order.payment_method,
        "item_total": float(order.item_total),
        "delivery_fee": float(order.delivery_fee),
        "total": float(order.total),
        "created_at": order.created_at.isoformat(),
        "items": [
            {
                "product_id": item.product_id,
                "name": item.product.name,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "line_total": float(item.line_total),
                "image": image_url(item.product.image, request),
            }
            for item in order.items.all()
        ],
    }


def find_user(identifier):
    return User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()


@require_http_methods(["GET"])
def config(request):
    return ok(
        {
            "service_city": SERVICE_CITY,
            "currency": "INR",
            "features": ["customer", "seller", "delivery", "shop-location"],
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def login(request):
    data = body_json(request)
    identifier = str(data.get("username") or data.get("email") or "").strip()
    password = data.get("password") or ""
    found = find_user(identifier)
    username = found.username if found else identifier
    user = authenticate(request, username=username, password=password)
    if not user:
        return error("Invalid username or password.", status=401)
    token = AuthToken.create_for_user(user)
    return ok({"token": token.token, "user": user_payload(user, request)})


@csrf_exempt
@require_http_methods(["POST"])
def register_customer(request):
    data = body_json(request)
    city = str(data.get("city") or SERVICE_CITY).strip()
    if city.lower() != SERVICE_CITY.lower():
        return error(f"AfriShop is currently available only in {SERVICE_CITY}.")
    username = str(data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return error("Username and password are required.")
    if User.objects.filter(username__iexact=username).exists():
        return error("Username already exists.")
    user = User.objects.create_user(
        username=username,
        password=password,
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
        email=data.get("email", ""),
    )
    CustomerProfile.objects.create(
        user=user,
        phone=data.get("phone", ""),
        address=data.get("address", f"{SERVICE_CITY}, Punjab"),
    )
    token = AuthToken.create_for_user(user)
    return ok({"token": token.token, "user": user_payload(user, request)}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
def register_seller(request):
    data = body_json(request)
    city = str(data.get("city") or SERVICE_CITY).strip()
    if city.lower() != SERVICE_CITY.lower():
        return error(f"Seller registration is currently open only in {SERVICE_CITY}.")
    username = str(data.get("username") or "").strip()
    password = data.get("password") or ""
    store_name = str(data.get("store_name") or "").strip()
    if not username or not password or not store_name:
        return error("Username, password, and store name are required.")
    if User.objects.filter(username__iexact=username).exists():
        return error("Username already exists.")
    user = User.objects.create_user(
        username=username,
        password=password,
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
        email=data.get("email", ""),
        is_staff=True,
    )
    Store.objects.create(
        owner=user,
        name=store_name,
        slug=unique_slug(Store, store_name),
        tagline=data.get("tagline", "Food Store"),
        description=data.get("description", "Fresh food listed on AfriShop."),
        phone=data.get("phone", ""),
        email=data.get("store_email", data.get("email", "")),
        city=SERVICE_CITY,
        address=data.get("address", f"{SERVICE_CITY}, Punjab"),
        latitude=decimal_value(data.get("latitude"), "30.901000"),
        longitude=decimal_value(data.get("longitude"), "75.857300"),
        delivery_fee=decimal_value(data.get("delivery_fee"), "30"),
        cover_image="shop/img/store-cover.jpg",
        logo_image="shop/img/logo-customer.jpg",
    )
    token = AuthToken.create_for_user(user)
    return ok({"token": token.token, "user": user_payload(user, request)}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
def register_delivery(request):
    data = body_json(request)
    city = str(data.get("city") or SERVICE_CITY).strip()
    if city.lower() != SERVICE_CITY.lower():
        return error(f"Delivery partner registration is currently open only in {SERVICE_CITY}.")
    username = str(data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return error("Username and password are required.")
    if User.objects.filter(username__iexact=username).exists():
        return error("Username already exists.")
    user = User.objects.create_user(
        username=username,
        password=password,
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
        email=data.get("email", ""),
    )
    DeliveryProfile.objects.create(
        user=user,
        phone=data.get("phone", ""),
        city=SERVICE_CITY,
        vehicle_type=data.get("vehicle_type", "Bike"),
        vehicle_number=data.get("vehicle_number", ""),
    )
    token = AuthToken.create_for_user(user)
    return ok({"token": token.token, "user": user_payload(user, request)}, status=201)


@require_http_methods(["GET"])
def categories(request):
    return ok({"categories": [category_payload(category) for category in Category.objects.all()]})


@require_http_methods(["GET"])
def stores(request):
    query = request.GET.get("q", "").strip()
    qs = Store.objects.filter(city__iexact=SERVICE_CITY, is_open=True)
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(tagline__icontains=query))
    return ok({"stores": [store_payload(store, request) for store in qs]})


@require_http_methods(["GET"])
def store_detail(request, slug):
    store = Store.objects.filter(slug=slug, city__iexact=SERVICE_CITY).first()
    if not store:
        return error("Store not found.", status=404)
    products = store.products.filter(active=True).select_related("category", "store")
    return ok(
        {
            "store": store_payload(store, request),
            "products": [product_payload(product, request) for product in products],
        }
    )


@require_http_methods(["GET"])
def products(request):
    query = request.GET.get("q", "").strip()
    qs = Product.objects.filter(active=True, store__city__iexact=SERVICE_CITY).select_related("store", "category")
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(store__name__icontains=query))
    return ok({"products": [product_payload(product, request) for product in qs.order_by("-featured", "name")]})


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_login_required
def orders(request):
    user = request.api_user
    if request.method == "GET":
        if hasattr(user, "store"):
            qs = user.store.orders.select_related("customer", "store", "delivery_partner").prefetch_related("items__product")
        elif hasattr(user, "delivery_profile"):
            qs = user.deliveries.select_related("customer", "store", "delivery_partner").prefetch_related("items__product")
        else:
            qs = user.orders.select_related("customer", "store", "delivery_partner").prefetch_related("items__product")
        return ok({"orders": [order_payload(order, request) for order in qs]})

    if hasattr(user, "store") or hasattr(user, "delivery_profile"):
        return error("Only customers can place orders.", status=403)
    data = body_json(request)
    items = data.get("items") or []
    if not items:
        return error("Order items are required.")
    product_ids = [item.get("product_id") for item in items]
    products_by_id = {
        product.id: product
        for product in Product.objects.filter(id__in=product_ids, active=True, store__city__iexact=SERVICE_CITY).select_related("store")
    }
    if len(products_by_id) != len(set(product_ids)):
        return error("One or more products are unavailable in Ludhiana.")
    stores_in_cart = {product.store_id for product in products_by_id.values()}
    if len(stores_in_cart) != 1:
        return error("Order items must be from one shop.")
    order_items = []
    item_total = Decimal("0.00")
    for item in items:
        product = products_by_id.get(item.get("product_id"))
        quantity = max(int(item.get("quantity") or 1), 1)
        if quantity > product.stock:
            return error(f"{product.name} has only {product.stock} left.")
        line_total = product.price * quantity
        item_total += line_total
        order_items.append((product, quantity))
    store = order_items[0][0].store
    profile = getattr(user, "customer_profile", None)
    with transaction.atomic():
        order = Order.objects.create(
            customer=user,
            store=store,
            status=Order.NEW,
            delivery_address=data.get("delivery_address") or (profile.address if profile else f"{SERVICE_CITY}, Punjab"),
            payment_method=data.get("payment_method") or Order.CASH,
            item_total=item_total,
            delivery_fee=store.delivery_fee,
        )
        for product, quantity in order_items:
            OrderItem.objects.create(order=order, product=product, quantity=quantity, unit_price=product.price)
            product.stock = max(product.stock - quantity, 0)
            product.save(update_fields=["stock"])
    order = Order.objects.select_related("customer", "store", "delivery_partner").prefetch_related("items__product").get(id=order.id)
    return ok({"order": order_payload(order, request)}, status=201)


@require_http_methods(["GET"])
@api_login_required
def order_detail(request, order_id):
    user = request.api_user
    qs = Order.objects.select_related("customer", "store", "delivery_partner").prefetch_related("items__product")
    if hasattr(user, "store"):
        qs = qs.filter(store=user.store)
    elif hasattr(user, "delivery_profile"):
        qs = qs.filter(delivery_partner=user)
    else:
        qs = qs.filter(customer=user)
    order = qs.filter(order_id=order_id).first()
    if not order:
        return error("Order not found.", status=404)
    return ok({"order": order_payload(order, request)})


@csrf_exempt
@require_http_methods(["GET", "POST"])
@seller_required
def seller_products(request):
    store = request.api_user.store
    if request.method == "GET":
        products_qs = store.products.select_related("store", "category")
        return ok({"products": [product_payload(product, request) for product in products_qs]})
    data = body_json(request)
    name = str(data.get("name") or "").strip()
    if not name:
        return error("Product name is required.")
    category = Category.objects.filter(id=data.get("category_id")).first() or Category.objects.first()
    product = Product.objects.create(
        store=store,
        category=category,
        name=name,
        slug=unique_slug(Product, name),
        description=data.get("description", ""),
        price=decimal_value(data.get("price"), "0"),
        image=data.get("image", "shop/img/product-indomie.jpg"),
        stock=max(int(data.get("stock") or 0), 0),
        active=bool(data.get("active", True)),
        featured=bool(data.get("featured", False)),
    )
    return ok({"product": product_payload(product, request)}, status=201)


@csrf_exempt
@require_http_methods(["PATCH", "POST"])
@seller_required
def seller_product_detail(request, product_id):
    product = request.api_user.store.products.select_related("store", "category").filter(id=product_id).first()
    if not product:
        return error("Product not found.", status=404)
    data = body_json(request)
    for field in ["name", "description", "image"]:
        if field in data:
            setattr(product, field, data[field])
    if "price" in data:
        product.price = decimal_value(data["price"], str(product.price))
    if "stock" in data:
        product.stock = max(int(data["stock"]), 0)
    if "active" in data:
        product.active = bool(data["active"])
    if "featured" in data:
        product.featured = bool(data["featured"])
    if "category_id" in data:
        category = Category.objects.filter(id=data["category_id"]).first()
        if category:
            product.category = category
    if "name" in data:
        product.slug = unique_slug(Product, product.name, current_id=product.id)
    product.save()
    return ok({"product": product_payload(product, request)})


@csrf_exempt
@require_http_methods(["POST"])
@seller_required
def seller_order_action(request, order_id):
    order = request.api_user.store.orders.filter(order_id=order_id).first()
    if not order:
        return error("Order not found.", status=404)
    action = body_json(request).get("action")
    transitions = {
        "accept": Order.PREPARING,
        "reject": Order.CANCELLED,
        "dispatch": Order.OUT_FOR_DELIVERY,
        "deliver": Order.DELIVERED,
    }
    if action not in transitions:
        return error("Unknown order action.")
    order.status = transitions[action]
    order.save(update_fields=["status", "updated_at"])
    order = Order.objects.select_related("customer", "store", "delivery_partner").prefetch_related("items__product").get(id=order.id)
    return ok({"order": order_payload(order, request)})


@require_http_methods(["GET"])
@delivery_required
def delivery_available_orders(request):
    orders_qs = (
        Order.objects.filter(store__city__iexact=SERVICE_CITY, delivery_partner__isnull=True, status=Order.PREPARING)
        .select_related("customer", "store", "delivery_partner")
        .prefetch_related("items__product")
    )
    return ok({"orders": [order_payload(order, request) for order in orders_qs]})


@csrf_exempt
@require_http_methods(["POST"])
@delivery_required
def delivery_accept_order(request, order_id):
    order = Order.objects.filter(order_id=order_id, delivery_partner__isnull=True, status=Order.PREPARING).first()
    if not order:
        return error("Order is no longer available.", status=409)
    order.delivery_partner = request.api_user
    order.status = Order.OUT_FOR_DELIVERY
    order.save(update_fields=["delivery_partner", "status", "updated_at"])
    request.api_user.delivery_profile.status = DeliveryProfile.BUSY
    request.api_user.delivery_profile.save(update_fields=["status"])
    order = Order.objects.select_related("customer", "store", "delivery_partner").prefetch_related("items__product").get(id=order.id)
    return ok({"order": order_payload(order, request)})


@csrf_exempt
@require_http_methods(["POST"])
@delivery_required
def delivery_update_order(request, order_id):
    order = request.api_user.deliveries.filter(order_id=order_id).first()
    if not order:
        return error("Order not found.", status=404)
    status = body_json(request).get("status")
    if status not in [Order.OUT_FOR_DELIVERY, Order.DELIVERED]:
        return error("Unsupported delivery status.")
    order.status = status
    order.save(update_fields=["status", "updated_at"])
    if status == Order.DELIVERED:
        request.api_user.delivery_profile.status = DeliveryProfile.AVAILABLE
        request.api_user.delivery_profile.save(update_fields=["status"])
    order = Order.objects.select_related("customer", "store", "delivery_partner").prefetch_related("items__product").get(id=order.id)
    return ok({"order": order_payload(order, request)})
