from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from .views import dashboard, health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("menu/", include("apps.menu.urls")),
    path("tables/", include("apps.dining.urls")),
    path("orders/", include("apps.orders.urls")),
    path("billing/", include("apps.billing.urls")),
    path("health/", health, name="health"),
    path("", dashboard, name="dashboard"),
]
