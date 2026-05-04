from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

from .forms import CheckoutForm, LoginForm, ProductForm, SignUpForm
from .models import Category, CustomerProfile, Order, OrderItem, Product, Store


def _find_user(identifier):
    user = User.objects.filter(username__iexact=identifier).first()
    if user:
        return user
    return User.objects.filter(
        Q(customer_profile__phone=identifier) | Q(store__phone=identifier)
    ).first()


def _authenticate_from_form(request, form):
    identifier = form.cleaned_data["username"].strip()
    user = _find_user(identifier)
    username = user.username if user else identifier
    return authenticate(request, username=username, password=form.cleaned_data["password"])


def _cart(request):
    return request.session.setdefault("cart", {})


def _cart_details(request):
    cart = _cart(request)
    ids = [int(product_id) for product_id in cart.keys()]
    products = Product.objects.filter(id__in=ids, active=True).select_related("store", "category")
    product_map = {str(product.id): product for product in products}
    items = []
    subtotal = Decimal("0.00")
    store = None
    for product_id, qty in cart.items():
        product = product_map.get(product_id)
        if not product:
            continue
        quantity = max(int(qty), 1)
        line_total = product.price * quantity
        subtotal += line_total
        store = store or product.store
        items.append(
            {
                "product": product,
                "quantity": quantity,
                "line_total": line_total,
            }
        )
    delivery_fee = store.delivery_fee if store and items else Decimal("0.00")
    return {
        "items": items,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "total": subtotal + delivery_fee,
        "store": store,
        "count": sum(item["quantity"] for item in items),
    }


def _cart_count(request):
    return sum(int(qty) for qty in _cart(request).values())


def _unique_slug(model, value, current_id=None):
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


def seller_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not hasattr(request.user, "store"):
            messages.error(request, "Seller access is required.")
            return redirect("seller_login")
        return view_func(request, *args, **kwargs)

    return wrapped


def splash(request):
    if request.user.is_authenticated:
        if hasattr(request.user, "store"):
            return redirect("seller_dashboard")
        return redirect("home")
    return render(request, "shop/splash.html")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("seller_dashboard" if hasattr(request.user, "store") else "home")

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = _authenticate_from_form(request, form)
        if user:
            login(request, user)
            return redirect("seller_dashboard" if hasattr(user, "store") else "home")
        messages.error(request, "Those credentials did not match an AfriShop account.")
    return render(request, "shop/login.html", {"form": form})


def seller_login(request):
    if request.user.is_authenticated and hasattr(request.user, "store"):
        return redirect("seller_dashboard")

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = _authenticate_from_form(request, form)
        if user and hasattr(user, "store"):
            login(request, user)
            return redirect("seller_dashboard")
        messages.error(request, "Use the seller account for your store.")
    return render(request, "shop/seller_login.html", {"form": form})


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = SignUpForm(request.POST or None, initial={"address": "Sarabha Nagar, Ludhiana, Punjab"})
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("home")
    return render(request, "shop/signup.html", {"form": form})


@login_required
def home(request):
    query = request.GET.get("q", "").strip()
    categories = Category.objects.all()
    stores = Store.objects.filter(is_open=True)
    products = Product.objects.filter(active=True).select_related("store", "category")
    if query:
        products = products.filter(Q(name__icontains=query) | Q(store__name__icontains=query))
        stores = stores.filter(Q(name__icontains=query) | Q(description__icontains=query))
    context = {
        "categories": categories,
        "stores": stores,
        "products": products.order_by("-featured", "name")[:8],
        "featured_store": stores.first(),
        "cart_count": _cart_count(request),
        "query": query,
        "active_tab": "home",
    }
    return render(request, "shop/home.html", context)


@login_required
def store_detail(request, slug):
    store = get_object_or_404(Store, slug=slug)
    category_slug = request.GET.get("category")
    products = store.products.filter(active=True).select_related("category")
    if category_slug:
        products = products.filter(category__slug=category_slug)
    return render(
        request,
        "shop/store_detail.html",
        {
            "store": store,
            "products": products,
            "categories": Category.objects.filter(products__store=store).distinct(),
            "selected_category": category_slug,
            "cart_count": _cart_count(request),
            "active_tab": "categories",
        },
    )


@login_required
def product_detail(request, slug):
    product = get_object_or_404(Product.objects.select_related("store", "category"), slug=slug, active=True)
    if request.method == "POST":
        return add_to_cart(request, product.id)
    return render(
        request,
        "shop/product_detail.html",
        {"product": product, "cart_count": _cart_count(request), "active_tab": "categories"},
    )


@login_required
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id, active=True)
    cart = _cart(request)

    # Keep the cart single-store so checkout can use one seller and one fee.
    details = _cart_details(request)
    if details["store"] and details["store"].id != product.store_id:
        cart.clear()
        messages.info(request, "Your cart was switched to this store.")

    product_key = str(product.id)
    cart[product_key] = min(int(cart.get(product_key, 0)) + 1, max(product.stock, 1))
    request.session.modified = True
    messages.success(request, f"{product.name} added to cart.")
    return redirect(request.POST.get("next") or product.get_absolute_url())


@login_required
def update_cart(request, product_id):
    cart = _cart(request)
    product_key = str(product_id)
    quantity = int(request.POST.get("quantity", 0))
    if quantity <= 0:
        cart.pop(product_key, None)
    else:
        product = get_object_or_404(Product, id=product_id)
        cart[product_key] = min(quantity, max(product.stock, 1))
    request.session.modified = True
    return redirect("cart")


@login_required
def cart(request):
    details = _cart_details(request)
    return render(request, "shop/cart.html", {**details, "cart_count": details["count"], "active_tab": "cart"})


@login_required
def checkout(request):
    details = _cart_details(request)
    if not details["items"]:
        messages.info(request, "Your cart is empty.")
        return redirect("home")

    profile = getattr(request.user, "customer_profile", None)
    initial = {"delivery_address": profile.address if profile else "", "payment_method": Order.CASH}
    form = CheckoutForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            order = form.save(commit=False)
            order.customer = request.user
            order.store = details["store"]
            order.item_total = details["subtotal"]
            order.delivery_fee = details["delivery_fee"]
            order.save()
            for item in details["items"]:
                product = item["product"]
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=item["quantity"],
                    unit_price=product.price,
                )
                product.stock = max(product.stock - item["quantity"], 0)
                product.save(update_fields=["stock"])
        request.session["cart"] = {}
        return redirect("order_confirmation", order_id=order.order_id)
    return render(
        request,
        "shop/checkout.html",
        {**details, "form": form, "cart_count": details["count"], "active_tab": "cart"},
    )


@login_required
def order_confirmation(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("store", "customer").prefetch_related("items__product"),
        order_id=order_id,
        customer=request.user,
    )
    return render(request, "shop/order_confirmation.html", {"order": order, "active_tab": "orders"})


@login_required
def order_tracking(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("store", "customer").prefetch_related("items__product"),
        order_id=order_id,
        customer=request.user,
    )
    steps = [
        (Order.NEW, "Order Confirmed"),
        (Order.PREPARING, "Preparing"),
        (Order.OUT_FOR_DELIVERY, "Out for Delivery"),
        (Order.DELIVERED, "Delivered"),
    ]
    status_order = [step[0] for step in steps]
    current_index = status_order.index(order.status) if order.status in status_order else -1
    return render(
        request,
        "shop/order_tracking.html",
        {"order": order, "steps": steps, "current_index": current_index, "active_tab": "orders"},
    )


@login_required
def customer_orders(request):
    orders = request.user.orders.select_related("store").prefetch_related("items__product")
    return render(request, "shop/orders.html", {"orders": orders, "active_tab": "orders"})


@login_required
def profile(request):
    orders = request.user.orders.select_related("store")[:3]
    return render(
        request,
        "shop/profile.html",
        {"profile": getattr(request.user, "customer_profile", None), "orders": orders, "active_tab": "profile"},
    )


@seller_required
def seller_dashboard(request):
    store = request.user.store
    orders = store.orders.prefetch_related("items")
    today = timezone.localdate()
    today_orders = orders.filter(created_at__date=today)
    completed = orders.filter(status=Order.DELIVERED)
    context = {
        "store": store,
        "today_sales": sum(order.total for order in today_orders.exclude(status=Order.CANCELLED)),
        "new_orders": orders.filter(status=Order.NEW).count(),
        "preparing_orders": orders.filter(status=Order.PREPARING).count(),
        "delivery_orders": orders.filter(status=Order.OUT_FOR_DELIVERY).count(),
        "completed_orders": completed.count(),
        "recent_orders": orders.select_related("customer")[:4],
        "week_points": [18, 34, 28, 45, 37, 52, 58],
        "active_tab": "dashboard",
    }
    return render(request, "shop/seller/dashboard.html", context)


@seller_required
def seller_orders(request):
    store = request.user.store
    status = request.GET.get("status", Order.NEW)
    orders = store.orders.select_related("customer").prefetch_related("items__product")
    if status != "all":
        orders = orders.filter(status=status)
    return render(
        request,
        "shop/seller/orders.html",
        {
            "orders": orders,
            "status": status,
            "statuses": Order.STATUS_CHOICES,
            "counts": {
                "new": store.orders.filter(status=Order.NEW).count(),
                "preparing": store.orders.filter(status=Order.PREPARING).count(),
                "out_for_delivery": store.orders.filter(status=Order.OUT_FOR_DELIVERY).count(),
                "delivered": store.orders.filter(status=Order.DELIVERED).count(),
            },
            "active_tab": "orders",
        },
    )


@seller_required
def seller_order_detail(request, order_id):
    order = get_object_or_404(
        request.user.store.orders.select_related("customer").prefetch_related("items__product"),
        order_id=order_id,
    )
    if request.method == "POST":
        action = request.POST.get("action")
        transitions = {
            "accept": Order.PREPARING,
            "reject": Order.CANCELLED,
            "dispatch": Order.OUT_FOR_DELIVERY,
            "deliver": Order.DELIVERED,
        }
        if action in transitions:
            order.status = transitions[action]
            order.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Order {order.order_id} updated.")
        return redirect("seller_order_detail", order_id=order.order_id)
    return render(request, "shop/seller/order_detail.html", {"order": order, "active_tab": "orders"})


@seller_required
def seller_products(request):
    products = request.user.store.products.select_related("category")
    return render(request, "shop/seller/products.html", {"products": products, "active_tab": "products"})


@seller_required
def seller_product_form(request, product_id=None):
    product = None
    if product_id:
        product = get_object_or_404(request.user.store.products, id=product_id)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        product = form.save(commit=False)
        product.store = request.user.store
        product.slug = _unique_slug(Product, product.name, current_id=product.id)
        product.save()
        form.save_m2m()
        messages.success(request, "Product saved.")
        return redirect("seller_products")
    return render(
        request,
        "shop/seller/product_form.html",
        {"form": form, "product": product, "active_tab": "products"},
    )


@seller_required
def seller_earnings(request):
    store = request.user.store
    completed = list(store.orders.filter(status=Order.DELIVERED).prefetch_related("items"))
    all_paid = list(store.orders.exclude(status=Order.CANCELLED).prefetch_related("items"))
    context = {
        "store": store,
        "month_earnings": sum(order.total for order in all_paid),
        "order_earnings": sum(order.item_total for order in all_paid),
        "delivery_earnings": sum(order.delivery_fee for order in all_paid),
        "total_orders": len(all_paid),
        "average_order": (sum(order.total for order in all_paid) / len(all_paid)) if all_paid else Decimal("0.00"),
        "recent_transactions": store.orders.exclude(status=Order.CANCELLED)[:5],
        "active_tab": "earnings",
    }
    return render(request, "shop/seller/earnings.html", context)


@seller_required
def seller_profile(request):
    return render(request, "shop/seller/profile.html", {"store": request.user.store, "active_tab": "more"})


@seller_required
def seller_notifications(request):
    orders = request.user.store.orders.select_related("customer")[:8]
    return render(request, "shop/seller/notifications.html", {"orders": orders, "active_tab": "more"})


@seller_required
def seller_settings(request):
    return render(request, "shop/seller/settings.html", {"store": request.user.store, "active_tab": "more"})
