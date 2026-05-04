from django.urls import path

from . import api

urlpatterns = [
    path("config/", api.config, name="api_config"),
    path("auth/login/", api.login, name="api_login"),
    path("auth/register/customer/", api.register_customer, name="api_register_customer"),
    path("auth/register/seller/", api.register_seller, name="api_register_seller"),
    path("auth/register/delivery/", api.register_delivery, name="api_register_delivery"),
    path("categories/", api.categories, name="api_categories"),
    path("stores/", api.stores, name="api_stores"),
    path("stores/<slug:slug>/", api.store_detail, name="api_store_detail"),
    path("products/", api.products, name="api_products"),
    path("orders/", api.orders, name="api_orders"),
    path("orders/<str:order_id>/", api.order_detail, name="api_order_detail"),
    path("seller/products/", api.seller_products, name="api_seller_products"),
    path("seller/products/<int:product_id>/", api.seller_product_detail, name="api_seller_product_detail"),
    path("seller/orders/<str:order_id>/action/", api.seller_order_action, name="api_seller_order_action"),
    path("delivery/orders/available/", api.delivery_available_orders, name="api_delivery_available_orders"),
    path("delivery/orders/<str:order_id>/accept/", api.delivery_accept_order, name="api_delivery_accept_order"),
    path("delivery/orders/<str:order_id>/status/", api.delivery_update_order, name="api_delivery_update_order"),
]
