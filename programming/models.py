from django.db import models
from django.db.models import F
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()


def validate_test_cases_json(value):
    """验证 test_cases 是列表"""
    if not isinstance(value, list):
        raise ValidationError("测试用例必须是 JSON 列表格式")


class CodeProblem(models.Model):
    """
    编程题目模型 (AcWing/LeetCode 风格)
    """
    # --- 基础信息 ---
    title = models.CharField(max_length=200, verbose_name="题目名称")
    description = models.TextField(verbose_name="题目描述 (支持 Markdown/MathJax)")

    # --- 函数补全模式核心字段 ---
    function_name = models.CharField(
        max_length=100,
        default='',
        blank=True,
        verbose_name="函数名",
        help_text="用户需要实现的函数名，例如: twoSum, add"
    )
    param_names = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="参数名 (逗号分隔)",
        help_text="例如: nums,target 或 a,b"
    )

    # --- 示例 (用于前端展示) ---
    input_example = models.JSONField(null=True, blank=True, verbose_name="输入示例")
    output_example = models.JSONField(null=True, blank=True, verbose_name="输出示例")

    # --- 结构化输入输出格式说明 ---
    input_format = models.TextField(blank=True, null=True, verbose_name="输入格式")
    output_format = models.TextField(blank=True, null=True, verbose_name="输出格式")

    # --- 数据范围与样例文本 ---
    data_range = models.TextField(blank=True, null=True, verbose_name="数据范围")
    sample_input = models.TextField(blank=True, null=True, verbose_name="样例输入")
    sample_output = models.TextField(blank=True, null=True, verbose_name="样例输出")

    # --- 判题核心 ---
    test_cases = models.JSONField(
        default=list,
        blank=True,
        verbose_name="测试用例集 (JSON)",
        validators=[validate_test_cases_json]
    )

    # --- 题解与视频讲解 ---
    solution_text = models.TextField(blank=True, null=True, verbose_name="官方题解")
    video_url = models.CharField(max_length=500, blank=True, null=True, verbose_name="视频链接")

    # --- 元数据 ---
    difficulty = models.CharField(
        max_length=20,
        choices=[('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')],
        default='medium',
        verbose_name="难度"
    )
    time_limit = models.IntegerField(default=1, verbose_name="时间限制 (秒)")
    memory_limit = models.IntegerField(default=128, verbose_name="内存限制 (MB)")
    source = models.CharField(max_length=100, blank=True, null=True, verbose_name="题目来源")
    tags = models.CharField(max_length=200, blank=True, null=True, verbose_name="算法标签")

    # --- 统计 ---
    accepted_count = models.PositiveIntegerField(default=0, verbose_name="通过人数")
    submission_count = models.PositiveIntegerField(default=0, verbose_name="总提交数")

    # --- 时间戳 ---
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "编程题目"
        verbose_name_plural = "编程题目管理"
        ordering = ['id']

    def __str__(self):
        return f"{self.id}. {self.title}"

    def get_tags_list(self):
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(',') if tag.strip()]


class CodeSubmission(models.Model):
    """
    代码提交记录模型
    """
    LANGUAGE_CHOICES = [
        ('python', 'Python 3'),
        ('c', 'C (GCC)'),
        ('cpp', 'C++ (G++)'),
        ('java', 'Java'),
    ]

    STATUS_CHOICES = [
        ('PD', 'Pending'),
        ('AC', 'Accepted'),
        ('WA', 'Wrong Answer'),
        ('TLE', 'Time Limit Exceeded'),
        ('MLE', 'Memory Limit Exceeded'),
        ('RE', 'Runtime Error'),
        ('CE', 'Compilation Error'),
    ]

    # 新增：作答模式
    MODE_CHOICES = [
        ('practice', '练习模式'),
        ('exam', '考试模式'),
    ]

    problem = models.ForeignKey(
        CodeProblem,
        on_delete=models.CASCADE,
        related_name='submissions',
        verbose_name="所属题目"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="提交用户"
    )
    code = models.TextField(verbose_name="提交代码")
    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default='python', verbose_name="编程语言")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PD', verbose_name="判题状态")

    # 新增字段：提交模式
    mode = models.CharField(
        max_length=20,
        choices=MODE_CHOICES,
        default='practice',
        verbose_name="作答模式"
    )

    feedback = models.TextField(null=True, blank=True, verbose_name="判题反馈")
    execution_time = models.IntegerField(default=0, null=True, blank=True, verbose_name="运行时间(ms)")
    execution_memory = models.IntegerField(default=0, null=True, blank=True, verbose_name="运行内存(KB)")
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name="提交时间")

    @property
    def is_correct(self):
        return self.status == 'AC'

    class Meta:
        verbose_name = "代码提交记录"
        verbose_name_plural = "代码提交记录"
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['user', '-submitted_at']),
            models.Index(fields=['problem', '-submitted_at']),
            models.Index(fields=['user', 'problem', 'mode']),
        ]

    def __str__(self):
        username = self.user.username if self.user else "匿名用户"
        return f"{username} - {self.problem.title} - {self.get_status_display()}"

    def save(self, *args, **kwargs):
        """
        统计逻辑说明：
        1. 新建提交时：submission_count + 1
        2. 新建且状态为 AC：accepted_count + 1
        3. 更新时如果状态从非 AC -> AC：accepted_count + 1
        4. 更新时如果状态从 AC -> 非 AC：accepted_count - 1
        """
        is_new = self.pk is None
        old_status = None

        if not is_new:
            old_obj = CodeSubmission.objects.filter(pk=self.pk).only('status').first()
            if old_obj:
                old_status = old_obj.status

        super().save(*args, **kwargs)

        if is_new:
            CodeProblem.objects.filter(pk=self.problem_id).update(
                submission_count=F('submission_count') + 1
            )
            if self.status == 'AC':
                CodeProblem.objects.filter(pk=self.problem_id).update(
                    accepted_count=F('accepted_count') + 1
                )
        else:
            if old_status != self.status:
                if old_status != 'AC' and self.status == 'AC':
                    CodeProblem.objects.filter(pk=self.problem_id).update(
                        accepted_count=F('accepted_count') + 1
                    )
                elif old_status == 'AC' and self.status != 'AC':
                    CodeProblem.objects.filter(pk=self.problem_id).update(
                        accepted_count=F('accepted_count') - 1
                    )


class ProblemDiscussion(models.Model):
    problem = models.ForeignKey(
        CodeProblem,
        on_delete=models.CASCADE,
        related_name='discussions',
        verbose_name="所属题目"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="发布用户"
    )
    title = models.CharField(max_length=200, verbose_name="讨论标题")
    content = models.TextField(verbose_name="讨论内容")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "题目讨论"
        verbose_name_plural = "题目讨论"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} by {self.user or 'Anonymous'}"


class ProblemFavorite(models.Model):
    """
    题目收藏模型
    一个用户只能收藏同一道题一次
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='favorite_problems',
        verbose_name="用户"
    )
    problem = models.ForeignKey(
        CodeProblem,
        on_delete=models.CASCADE,
        related_name='favorited_users',
        verbose_name="题目"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="收藏时间")

    class Meta:
        verbose_name = "题目收藏"
        verbose_name_plural = "题目收藏"
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'problem'],
                name='unique_user_problem_favorite'
            )
        ]
        indexes = [
            models.Index(fields=['user', 'problem']),
        ]

    def __str__(self):
        return f"{self.user} 收藏了 {self.problem}"