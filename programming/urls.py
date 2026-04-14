from django.urls import path

from . import views

app_name = 'programming'

urlpatterns = [
    # 题库分区首页
    path('zones/', views.problem_zones, name='problem_zones'),

    # 学习推荐页（新增）
    path('recommendation/', views.recommendation_home, name='recommendation_home'),

    # 分区详情页
    path('zones/<slug:zone_slug>/', views.problem_zone_detail, name='problem_zone_detail'),

    # 全部题目页（保留，作为辅助入口）
    path('problems/', views.problem_list, name='problem_list'),

    # 题目详情页
    path('problems/<int:pk>/', views.problem_detail, name='problem_detail'),

    # 选择当前题目的作答模式
    path('problems/<int:pk>/select-mode/', views.select_problem_mode, name='select_problem_mode'),

    # 收藏 / 取消收藏题目
    path('problems/<int:pk>/toggle-favorite/', views.toggle_problem_favorite, name='toggle_problem_favorite'),

    # 提交代码页
    path('problems/<int:pk>/submit/', views.submit_code, name='submit_code'),

    # AI 助手接口
    path('problems/<int:pk>/ai-assistant/', views.ai_assistant_api, name='ai_assistant_api'),

    # 运行测试页
    path('problems/<int:pk>/run_test/', views.run_test, name='run_test'),

    # 摄像头页面
    path('camera/', views.camera_view, name='camera'),

    # 人脸检测 API
    path('api/detect-face/', views.detect_face_api, name='detect_face_api'),

    # 提交记录列表
    path('submissions/', views.submission_list, name='submission_list'),

    # 提交记录详情
    path('submissions/<int:pk>/', views.submission_detail, name='submission_detail'),
]
