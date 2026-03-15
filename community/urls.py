from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

app_name = 'community'

urlpatterns = [
    # 首页与列表
    path('', views.category_list, name='community_home'),
    path('category/<int:category_id>/', views.post_list, name='post_list'),
    
    # 帖子详情与操作
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('post/create/', views.create_post, name='create_post'),
    path('post/<int:post_id>/like/', views.toggle_like, name='toggle_like'),
    
    # 图片上传 (CKEditor 专用)
    path('upload/', views.upload_image, name='upload_image'),
]

# 仅在开发环境下提供媒体文件服务
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)