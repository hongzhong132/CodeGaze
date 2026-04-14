from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F
from django.utils import timezone

User = get_user_model()


def validate_test_cases_json(value):
    """验证 test_cases 是列表"""
    if not isinstance(value, list):
        raise ValidationError("测试用例必须是 JSON 列表格式")


class CodeProblem(models.Model):
    """
    编程题目模型。
    在原有题目结构上增加分类、知识点、推荐权重等字段，
    为教师分析和学生个性化推荐提供基础。
    """

    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]

    CATEGORY_CHOICES = [
        ('基础', '基础'),
        ('数组', '数组'),
        ('字符串', '字符串'),
        ('哈希', '哈希'),
        ('双指针', '双指针'),
        ('栈', '栈 / 队列'),
        ('链表', '链表'),
        ('二分', '二分查找'),
        ('贪心', '贪心'),
        ('动态规划', '动态规划'),
        ('树', '树'),
        ('图', '图'),
        ('回溯', '回溯'),
        ('数学', '数学'),
    ]

    STAGE_CHOICES = [
        ('入门', '入门'),
        ('提升', '提升'),
        ('进阶', '进阶'),
        ('冲刺', '冲刺'),
    ]

    QUESTION_TYPE_CHOICES = [
        ('function', '函数补全'),
        ('acm', '标准输入输出'),
    ]

    # --- 基础信息 ---
    title = models.CharField(max_length=200, verbose_name="题目名称")
    description = models.TextField(verbose_name="题目描述 (支持 Markdown/MathJax)")

    # --- 题目结构化字段 ---
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='基础',
        verbose_name="主分类",
        help_text="例如：数组、动态规划、树、图等",
    )
    knowledge_points = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name="知识点",
        help_text="多个知识点使用英文逗号分隔，例如：前缀和,枚举,边界处理",
    )
    supported_languages = models.CharField(
        max_length=255,
        blank=True,
        default='python,c,cpp,java',
        verbose_name="支持语言",
        help_text="多个语言使用英文逗号分隔，例如：python,cpp,java",
    )
    estimated_minutes = models.PositiveIntegerField(
        default=15,
        verbose_name="预估完成时长（分钟）",
    )
    recommend_stage = models.CharField(
        max_length=20,
        choices=STAGE_CHOICES,
        default='入门',
        verbose_name="推荐阶段",
    )
    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPE_CHOICES,
        default='function',
        verbose_name="题目形式",
    )

    # --- 个性化推荐辅助字段（新增） ---
    recommendation_weight = models.PositiveIntegerField(
        default=1,
        verbose_name='推荐权重',
        help_text='数值越高，越容易在推荐列表中靠前显示。',
    )
    is_for_weakness_fix = models.BooleanField(
        default=True,
        verbose_name='适合补弱',
    )
    is_for_improvement = models.BooleanField(
        default=True,
        verbose_name='适合巩固提升',
    )
    is_for_challenge = models.BooleanField(
        default=False,
        verbose_name='适合挑战拓展',
    )

    # --- 函数补全模式核心字段 ---
    function_name = models.CharField(
        max_length=100,
        default='',
        blank=True,
        verbose_name="函数名",
        help_text="用户需要实现的函数名，例如: twoSum, add",
    )
    param_names = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="参数名 (逗号分隔)",
        help_text="例如: nums,target 或 a,b",
    )

    # --- 示例 ---
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
        validators=[validate_test_cases_json],
    )

    # --- 题解与视频讲解 ---
    solution_text = models.TextField(blank=True, null=True, verbose_name="官方题解")
    video_url = models.CharField(max_length=500, blank=True, null=True, verbose_name="视频链接")

    # --- 元数据 ---
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default='medium',
        verbose_name="难度",
    )
    time_limit = models.IntegerField(default=1, verbose_name="时间限制 (秒)")
    memory_limit = models.IntegerField(default=128, verbose_name="内存限制 (MB)")
    source = models.CharField(max_length=100, blank=True, null=True, verbose_name="题目来源")
    tags = models.CharField(max_length=255, blank=True, default='', verbose_name="算法标签")

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
        indexes = [
            models.Index(fields=['difficulty']),
            models.Index(fields=['category']),
            models.Index(fields=['recommend_stage']),
            models.Index(fields=['source']),
            models.Index(fields=['recommendation_weight']),
        ]

    def __str__(self):
        return f"{self.id}. {self.title}"

    def _split_csv_field(self, field_value):
        if not field_value:
            return []
        return [item.strip() for item in str(field_value).split(',') if item.strip()]

    def get_tags_list(self):
        return self._split_csv_field(self.tags)

    def get_knowledge_points_list(self):
        return self._split_csv_field(self.knowledge_points)

    def get_supported_languages_list(self):
        return self._split_csv_field(self.supported_languages)

    @property
    def acceptance_rate(self):
        if not self.submission_count:
            return 0
        return round(self.accepted_count * 100 / self.submission_count, 2)


class CodeSubmission(models.Model):
    """代码提交记录模型"""

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

    MODE_CHOICES = [
        ('practice', '练习模式'),
        ('exam', '考试模式'),
    ]

    problem = models.ForeignKey(
        CodeProblem,
        on_delete=models.CASCADE,
        related_name='submissions',
        verbose_name="所属题目",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="提交用户",
    )
    code = models.TextField(verbose_name="提交代码")
    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default='python', verbose_name="编程语言")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PD', verbose_name="判题状态")
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default='practice', verbose_name="作答模式")

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
            models.Index(fields=['status']),
            models.Index(fields=['language']),
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
                submission_count=F('submission_count') + 1,
            )
            if self.status == 'AC':
                CodeProblem.objects.filter(pk=self.problem_id).update(
                    accepted_count=F('accepted_count') + 1,
                )
        else:
            if old_status != self.status:
                if old_status != 'AC' and self.status == 'AC':
                    CodeProblem.objects.filter(pk=self.problem_id).update(
                        accepted_count=F('accepted_count') + 1,
                    )
                elif old_status == 'AC' and self.status != 'AC':
                    CodeProblem.objects.filter(pk=self.problem_id).update(
                        accepted_count=F('accepted_count') - 1,
                    )


class ProblemDiscussion(models.Model):
    problem = models.ForeignKey(
        CodeProblem,
        on_delete=models.CASCADE,
        related_name='discussions',
        verbose_name="所属题目",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="发布用户",
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
    题目收藏模型。
    一个用户只能收藏同一道题一次。
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='favorite_problems',
        verbose_name="用户",
    )
    problem = models.ForeignKey(
        CodeProblem,
        on_delete=models.CASCADE,
        related_name='favorited_users',
        verbose_name="题目",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="收藏时间")

    class Meta:
        verbose_name = "题目收藏"
        verbose_name_plural = "题目收藏"
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'problem'],
                name='unique_user_problem_favorite',
            )
        ]
        indexes = [
            models.Index(fields=['user', 'problem']),
        ]

    def __str__(self):
        return f"{self.user} 收藏了 {self.problem}"


class UserProblemStatus(models.Model):
    STATUS_CHOICES = [
        ('not_started', '未做'),
        ('tried', '已尝试'),
        ('passed', '已通过'),
        ('needs_work', '待攻克'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='problem_statuses',
        verbose_name='用户',
    )
    problem = models.ForeignKey(
        CodeProblem,
        on_delete=models.CASCADE,
        related_name='user_statuses',
        verbose_name='题目',
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='not_started',
        verbose_name='学习状态',
    )
    attempt_count = models.PositiveIntegerField(default=0, verbose_name='尝试次数')
    passed_count = models.PositiveIntegerField(default=0, verbose_name='通过次数')
    first_passed_at = models.DateTimeField(null=True, blank=True, verbose_name='首次通过时间')
    last_submit_at = models.DateTimeField(null=True, blank=True, verbose_name='最近提交时间')
    wrong_count = models.PositiveIntegerField(default=0, verbose_name='错误次数')
    is_favorite = models.BooleanField(default=False, verbose_name='是否收藏')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '用户题目状态'
        verbose_name_plural = '用户题目状态'
        unique_together = ('user', 'problem')
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['problem', 'status']),
            models.Index(fields=['user', 'problem']),
        ]

    def __str__(self):
        return f'{self.user} - {self.problem} - {self.get_status_display()}'

    def refresh_from_activity(self, save=True):
        """根据提交记录和收藏状态，同步当前用户对当前题目的学习状态。"""
        submissions = CodeSubmission.objects.filter(
            user=self.user,
            problem=self.problem,
        ).order_by('submitted_at')

        attempt_count = submissions.count()
        passed_submissions = submissions.filter(status='AC')
        passed_count = passed_submissions.count()
        wrong_count = submissions.exclude(status__in=['AC', 'PD']).count()
        last_submission = submissions.order_by('-submitted_at').first()
        is_favorite = ProblemFavorite.objects.filter(user=self.user, problem=self.problem).exists()

        if passed_count > 0:
            new_status = 'passed'
        elif attempt_count == 0:
            new_status = 'not_started'
        elif wrong_count >= 2:
            new_status = 'needs_work'
        else:
            new_status = 'tried'

        first_pass_submission = passed_submissions.order_by('submitted_at').first()

        self.status = new_status
        self.attempt_count = attempt_count
        self.passed_count = passed_count
        self.wrong_count = wrong_count
        self.last_submit_at = last_submission.submitted_at if last_submission else None
        self.is_favorite = is_favorite

        if first_pass_submission and not self.first_passed_at:
            self.first_passed_at = first_pass_submission.submitted_at
        elif first_pass_submission:
            self.first_passed_at = first_pass_submission.submitted_at
        elif passed_count == 0:
            self.first_passed_at = None

        if save:
            self.save(update_fields=[
                'status',
                'attempt_count',
                'passed_count',
                'wrong_count',
                'last_submit_at',
                'first_passed_at',
                'is_favorite',
                'updated_at',
            ])
        return self

    @classmethod
    def sync_for_user_problem(cls, user, problem):
        if not user or not getattr(user, 'is_authenticated', False):
            return None
        obj, _ = cls.objects.get_or_create(user=user, problem=problem)
        return obj.refresh_from_activity(save=True)
