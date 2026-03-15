from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from codegaze.views import home_redirect

urlpatterns = [
    path("admin/", admin.site.urls),

    # 根路径：首页先判断是否登录
    path("", home_redirect, name="home"),

    # 账号模块
    path("accounts/", include("accounts.urls")),

    # 其他模块
    path("community/", include("community.urls")),
    path("", include("programming.urls")),
]

# 开发环境下提供媒体文件访问
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)