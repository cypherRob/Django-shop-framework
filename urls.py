from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("", views.splash, name="splash"),
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("home/", views.home, name="home"),
    path("stores/<slug:slug>/", views.store_detail, name="store_detail"),
    path("products/<slug:slug>/", views.product_detail, name="product_detail"),
    path("cart/", views.cart, name="cart"),
    path("cart/add/<int:product_id>/", views.add_to_cart, name="add_to_cart"),
    path("cart/update/<int:product_id>/", views.update_cart, name="update_cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("orders/", views.customer_orders, name="customer_orders"),
    path("orders/<str:order_id>/", views.order_confirmation, name="order_confirmation"),
    path("orders/<str:order_id>/tracking/", views.order_tracking, name="order_tracking"),
    path("profile/", views.profile, name="profile"),
    path("seller/login/", views.seller_login, name="seller_login"),
    path("seller/", views.seller_dashboard, name="seller_dashboard"),
    path("seller/orders/", views.seller_orders, name="seller_orders"),
    path("seller/orders/<str:order_id>/", views.seller_order_detail, name="seller_order_detail"),
    path("seller/products/", views.seller_products, name="seller_products"),
    path("seller/products/new/", views.seller_product_form, name="seller_product_new"),
    path("seller/products/<int:product_id>/edit/", views.seller_product_form, name="seller_product_edit"),
    path("seller/earnings/", views.seller_earnings, name="seller_earnings"),
    path("seller/profile/", views.seller_profile, name="seller_profile"),
    path("seller/notifications/", views.seller_notifications, name="seller_notifications"),
    path("seller/settings/", views.seller_settings, name="seller_settings"),
]
