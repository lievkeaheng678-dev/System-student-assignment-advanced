from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Student Portal admin"
admin.site.site_title = "Student Portal admin"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
]
