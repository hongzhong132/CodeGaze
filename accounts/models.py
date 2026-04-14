from django.contrib.auth.models import User
from django.db import models


def user_avatar_upload_to(instance, filename):
    return f"avatars/user_{instance.user_id}/{filename}"


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('student', '学生'),
        ('teacher', '教师'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='用户'
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='student',
        verbose_name='角色'
    )

    real_name = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='真实姓名'
    )

    nickname = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='昵称'
    )

    bio = models.TextField(
        blank=True,
        default='',
        verbose_name='个性签名 / 简介'
    )

    student_no = models.CharField(
        max_length=30,
        blank=True,
        default='',
        verbose_name='学号'
    )

    teacher_no = models.CharField(
        max_length=30,
        blank=True,
        default='',
        verbose_name='工号'
    )

    avatar = models.ImageField(
        upload_to=user_avatar_upload_to,
        blank=True,
        null=True,
        verbose_name='头像'
    )

    class Meta:
        verbose_name = '用户资料'
        verbose_name_plural = '用户资料'

    def __str__(self):
        display_name = self.nickname or self.real_name or self.user.username
        return f'{display_name} - {self.get_role_display()}'