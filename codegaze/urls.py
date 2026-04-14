from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from codegaze.views import home_redirect

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home_redirect, name="home"),
    path("accounts/", include("accounts.urls")),
    path("teacher/", include("teacher.urls")),
    path("community/", include("community.urls")),
    path("", include("programming.urls")),
    path("management/", include("management.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
