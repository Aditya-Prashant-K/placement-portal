from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Django's built-in admin is only a raw database inspector here.
    # The real "Placement Cell Admin" portal lives under /admin-portal/.
    path("django-admin/", admin.site.urls),
    path("", include("portal.urls")),
]
