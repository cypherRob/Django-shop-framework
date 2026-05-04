from django.contrib import admin

from .models import AuthToken, Category, CustomerProfile, DeliveryProfile, Order, OrderItem, Product, Store


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "icon")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "city", "phone", "is_open", "rating")
    list_filter = ("is_open", "city")
    search_fields = ("name", "owner__username", "address")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "store", "category", "price", "stock", "active", "featured")
    list_filter = ("active", "featured", "category", "store")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "address")
    search_fields = ("user__username", "phone", "address")


@admin.register(DeliveryProfile)
class DeliveryProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "city", "vehicle_type", "status")
    list_filter = ("city", "status")
    search_fields = ("user__username", "phone", "vehicle_number")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("line_total",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_id", "customer", "store", "delivery_partner", "status", "item_total", "delivery_fee", "created_at")
    list_filter = ("status", "payment_method", "store")
    search_fields = ("order_id", "customer__username", "delivery_address")
    readonly_fields = ("order_id", "created_at", "updated_at")
    inlines = [OrderItemInline]


@admin.register(AuthToken)
class AuthTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")
    search_fields = ("user__username", "token")
    readonly_fields = ("token", "created_at")
