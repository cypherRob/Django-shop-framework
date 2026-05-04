from decimal import Decimal
import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True)
    icon = models.CharField(max_length=40, default="shopping-bag")
    color = models.CharField(max_length=20, default="#147A32")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Store(models.Model):
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="store",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=130, unique=True)
    tagline = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    city = models.CharField(max_length=80, default="Ludhiana")
    address = models.CharField(max_length=240)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    opening_hours = models.CharField(max_length=120, default="9:00 AM - 10:00 PM")
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=Decimal("4.6"))
    delivery_minutes_min = models.PositiveIntegerField(default=30)
    delivery_minutes_max = models.PositiveIntegerField(default=40)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("30.00"))
    cover_image = models.CharField(max_length=180, default="shop/img/store-cover.jpg")
    logo_image = models.CharField(max_length=180, default="shop/img/logo-customer.jpg")
    is_open = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("store_detail", args=[self.slug])

    @property
    def delivery_window(self):
        return f"{self.delivery_minutes_min} - {self.delivery_minutes_max} min"

    @property
    def maps_url(self):
        if self.latitude is not None and self.longitude is not None:
            return f"https://www.google.com/maps/search/?api=1&query={self.latitude},{self.longitude}"
        return f"https://www.google.com/maps/search/?api=1&query={self.address.replace(' ', '+')}"


class Product(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name="products")
    name = models.CharField(max_length=140)
    slug = models.SlugField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    image = models.CharField(max_length=180, default="shop/img/product-indomie.jpg")
    stock = models.PositiveIntegerField(default=20)
    active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("product_detail", args=[self.slug])

    @property
    def in_stock(self):
        return self.active and self.stock > 0


class CustomerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=240, default="Sarabha Nagar, Ludhiana, Punjab")

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class DeliveryProfile(models.Model):
    AVAILABLE = "available"
    BUSY = "busy"
    OFFLINE = "offline"
    STATUS_CHOICES = [
        (AVAILABLE, "Available"),
        (BUSY, "Busy"),
        (OFFLINE, "Offline"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="delivery_profile",
    )
    phone = models.CharField(max_length=30)
    city = models.CharField(max_length=80, default="Ludhiana")
    vehicle_type = models.CharField(max_length=80, default="Bike")
    vehicle_number = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=AVAILABLE)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Order(models.Model):
    NEW = "new"
    PREPARING = "preparing"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (NEW, "New"),
        (PREPARING, "Preparing"),
        (OUT_FOR_DELIVERY, "Out for Delivery"),
        (DELIVERED, "Delivered"),
        (CANCELLED, "Cancelled"),
    ]

    CASH = "cash"
    UPI = "upi"
    CARD = "card"
    WALLET = "wallet"
    PAYMENT_CHOICES = [
        (CASH, "Cash on Delivery"),
        (UPI, "UPI"),
        (CARD, "Card"),
        (WALLET, "Wallet"),
    ]

    order_id = models.CharField(max_length=20, unique=True, blank=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="orders")
    delivery_partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deliveries",
    )
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=NEW)
    delivery_address = models.CharField(max_length=240)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default=CASH)
    item_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("30.00"))
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.order_id or f"Order #{self.pk}"

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.order_id:
            self.order_id = f"AFS{self.pk:06d}"
            super().save(update_fields=["order_id"])

    @property
    def total(self):
        return self.item_total + self.delivery_fee


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    @property
    def line_total(self):
        return self.quantity * self.unit_price


class AuthToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mobile_tokens")
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} token"

    @classmethod
    def create_for_user(cls, user):
        return cls.objects.create(user=user, token=secrets.token_urlsafe(32))
