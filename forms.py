from django import forms
from django.contrib.auth.models import User

from .models import CustomerProfile, Order, Product


class LoginForm(forms.Form):
    username = forms.CharField(label="Username or phone", max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)


class SignUpForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    phone = forms.CharField(max_length=30)
    address = forms.CharField(max_length=240)

    class Meta:
        model = User
        fields = ["first_name", "username", "email", "password", "phone", "address"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            CustomerProfile.objects.create(
                user=user,
                phone=self.cleaned_data["phone"],
                address=self.cleaned_data["address"],
            )
        return user


class CheckoutForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["delivery_address", "payment_method"]
        widgets = {
            "delivery_address": forms.TextInput(attrs={"placeholder": "Delivery address"}),
            "payment_method": forms.RadioSelect,
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "category", "description", "price", "stock", "image", "active", "featured"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "image": forms.TextInput(attrs={"placeholder": "shop/img/product-indomie.jpg"}),
        }
