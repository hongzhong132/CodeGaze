from django.contrib import admin
from django import forms
from django.contrib import messages
from collections import defaultdict

from .models import CodeProblem, CodeSubmission, ProblemDiscussion, ProblemFavorite
from .forms import CodeSubmissionAdminForm


# ==============================
# 自定义表单：为 CodeProblem 的 test_cases 提供更好的编辑控件
# ==============================
class CodeProblemForm(forms.ModelForm):
    class Meta:
        model = CodeProblem
        fields = '__all__'
        widgets = {
            'test_cases': forms.Textarea(attrs={
                'rows': 8,
                'style': 'font-family: monospace; font-size: 12px;',
                'placeholder': '[{"input": "1 2", "output": "3"}]'
            }),
            'description': forms.Textarea(attrs={
                'rows': 8,
                'style': 'font-family: monospace;'
            }),
            'solution_text': forms.Textarea(attrs={
                'rows': 8,
                'style': 'font-family: monospace;'
            }),
            'input_format': forms.Textarea(attrs={
                'rows': 4,
                'style': 'font-family: monospace;'
            }),
            'output_format': forms.Textarea(attrs={
                'rows': 4,
                'style': 'font-family: monospace;'
            }),
            'data_range': forms.Textarea(attrs={
                'rows': 4,
                'style': 'font-family: monospace;'
            }),
            'sample_input': forms.Textarea(attrs={
                'rows': 4,
                'style': 'font-family: monospace;'
            }),
            'sample_output': forms.Textarea(attrs={
                'rows': 4,
                'style': 'font-family: monospace;'
            }),
        }


# ==============================
# 清理重复题目的 Action
# ==============================
def clean_duplicate_problems(modeladmin, request, queryset):
    """
    清理整个数据库中标题重复的题目，仅保留每个标题中 ID 最小的一个。
    注意：此操作不可逆，请先备份数据库。
    """
    title_map = defaultdict(list)
    for p in CodeProblem.objects.all():
        title_map[p.title].append(p)

    deleted_count = 0
    for title, problems in title_map.items():
        if len(problems) > 1:
            keep = min(problems, key=lambda x: x.id)
            for p in problems:
                if p.id != keep.id:
                    p.delete()
                    deleted_count += 1

    modeladmin.message_user(
        request,
        f"已删除 {deleted_count} 个重复题目。",
        level=messages.SUCCESS
    )


clean_duplicate_problems.short_description = "清理重复题目（保留每个标题ID最小的记录）"


# ==============================
# CodeProblem 管理
# ==============================
@admin.register(CodeProblem)
class CodeProblemAdmin(admin.ModelAdmin):
    form = CodeProblemForm

    list_display = (
        'id',
        'title',
        'difficulty',
        'source',
        'accepted_count',
        'submission_count',
        'favorite_count',
        'created_at',
        'updated_at',
    )
    list_filter = ('difficulty', 'source', 'created_at', 'updated_at')
    search_fields = ('title', 'description', 'tags', 'source')
    list_editable = ('difficulty',)
    actions = [clean_duplicate_problems]

    fieldsets = (
        ('📌 基础信息', {
            'fields': ('title', 'difficulty', 'source', 'tags'),
            'description': '题目的基本元数据。'
        }),
        ('🧩 函数补全配置', {
            'fields': ('function_name', 'param_names', 'input_example', 'output_example'),
            'classes': ('collapse',),
            'description': '用于函数补全模式的函数定义与示例配置。'
        }),
        ('📝 题目描述', {
            'fields': ('description', 'input_format', 'output_format', 'data_range', 'sample_input', 'sample_output'),
            'classes': ('collapse',)
        }),
        ('⚙️ 判题配置', {
            'fields': ('test_cases', 'time_limit', 'memory_limit'),
            'classes': ('collapse',)
        }),
        ('📚 题解与视频', {
            'fields': ('solution_text', 'video_url')
        }),
        ('📊 统计数据', {
            'fields': ('accepted_count', 'submission_count'),
            'classes': ('collapse',)
        }),
        ('🕒 时间信息', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def favorite_count(self, obj):
        return obj.favorited_users.count()
    favorite_count.short_description = "收藏数"


# ==============================
# CodeSubmission 管理
# ==============================
@admin.register(CodeSubmission)
class CodeSubmissionAdmin(admin.ModelAdmin):
    form = CodeSubmissionAdminForm

    list_display = (
        'id',
        'problem_title',
        'user_username',
        'mode',
        'status',
        'language',
        'execution_time_display',
        'memory_usage',
        'submitted_at',
    )
    list_filter = ('mode', 'status', 'language', 'submitted_at', 'problem__difficulty')
    search_fields = ('user__username', 'problem__title', 'code')

    readonly_fields = (
        'status',
        'feedback',
        'execution_time',
        'execution_memory',
        'submitted_at',
        'is_correct',
    )

    fieldsets = (
        ('提交信息', {
            'fields': ('problem', 'user', 'language', 'mode', 'submitted_at')
        }),
        ('判题结果', {
            'fields': ('status', 'is_correct', 'execution_time', 'execution_memory', 'feedback')
        }),
        ('代码内容', {
            'fields': ('code',),
            'classes': ('collapse',),
            'description': '提交的源代码内容'
        }),
    )

    def has_add_permission(self, request):
        return True

    def problem_title(self, obj):
        return obj.problem.title if obj.problem else "-"
    problem_title.short_description = "题目"
    problem_title.admin_order_field = 'problem__title'

    def user_username(self, obj):
        return obj.user.username if obj.user else "Anonymous"
    user_username.short_description = "用户"
    user_username.admin_order_field = 'user__username'

    def memory_usage(self, obj):
        return f"{obj.execution_memory} KB" if obj.execution_memory else "0 KB"
    memory_usage.short_description = "内存"

    def execution_time_display(self, obj):
        return f"{obj.execution_time} ms" if obj.execution_time else "0 ms"
    execution_time_display.short_description = "耗时"


# ==============================
# ProblemDiscussion 管理
# ==============================
@admin.register(ProblemDiscussion)
class ProblemDiscussionAdmin(admin.ModelAdmin):
    list_display = ('id', 'problem_title', 'user_username', 'title_preview', 'created_at')
    list_filter = ('created_at', 'problem__difficulty')
    search_fields = ('title', 'content', 'user__username', 'problem__title')

    readonly_fields = ('problem', 'user', 'created_at', 'updated_at')

    fieldsets = (
        ('讨论信息', {
            'fields': ('problem', 'user', 'title', 'created_at', 'updated_at')
        }),
        ('内容', {
            'fields': ('content',)
        }),
    )

    def problem_title(self, obj):
        return obj.problem.title if obj.problem else "-"
    problem_title.short_description = "关联题目"

    def user_username(self, obj):
        return obj.user.username if obj.user else "Anonymous"
    user_username.short_description = "作者"

    def title_preview(self, obj):
        if obj.title and len(obj.title) > 30:
            return obj.title[:30] + "..."
        return obj.title or "-"
    title_preview.short_description = "标题"


# ==============================
# ProblemFavorite 管理
# ==============================
@admin.register(ProblemFavorite)
class ProblemFavoriteAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'problem', 'created_at')
    list_filter = ('created_at', 'problem__difficulty')
    search_fields = ('user__username', 'problem__title')
    readonly_fields = ('created_at',)

    fieldsets = (
        ('收藏信息', {
            'fields': ('user', 'problem', 'created_at')
        }),
    )