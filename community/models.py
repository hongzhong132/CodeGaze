from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# ⚠️ 已移除: from ckeditor.fields import RichTextField
# 我们不再使用 django-ckeditor 后端插件，改用原生 TextField + 前端 JS

class Category(models.Model):
    """话题分类"""
    name = models.CharField(max_length=100, verbose_name="分类名称")
    description = models.TextField(blank=True, verbose_name="简介")
    icon = models.CharField(max_length=50, default="bi-chat-left-text", verbose_name="图标类名") # 用于 Bootstrap Icons
    
    class Meta:
        verbose_name = "分类"
        verbose_name_plural = "分类"

    def __str__(self):
        return self.name

class Post(models.Model):
    """帖子"""
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='posts', verbose_name="分类")
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="作者")
    title = models.CharField(max_length=200, verbose_name="标题")
    is_pinned = models.BooleanField(default=False, verbose_name="是否置顶")
    
    # ✅ 修改点：使用标准的 TextField 替代 RichTextField
    # 这样就不需要依赖 ckeditor 的模板文件了
    content = models.TextField(verbose_name="内容")
    
    created_at = models.DateTimeField(default=timezone.now, verbose_name="发布时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="最后更新")
    views = models.PositiveIntegerField(default=0, verbose_name="浏览量")
    
    # 点赞数字段 (用于快速展示，实际逻辑由 PostLike 表控制)
    likes_count = models.PositiveIntegerField(default=0, verbose_name="点赞数")

    class Meta:
        ordering = ['-created_at'] # 默认按最新时间排序
        verbose_name = "帖子"
        verbose_name_plural = "帖子"

    def __str__(self):
        return self.title
    
    # 辅助方法：获取当前帖子的点赞用户列表（可选，用于模板判断是否已赞）
    def get_liked_users(self):
        return self.likes.all()

class Comment(models.Model):
    """评论/回复"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments', verbose_name="所属帖子")
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="评论者")
    content = models.TextField(verbose_name="评论内容")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="评论时间")

    class Meta:
        ordering = ['created_at']
        verbose_name = "评论"
        verbose_name_plural = "评论"

    def __str__(self):
        return f"Comment by {self.author.username}"

# 3. 新增：点赞记录模型 (防止重复点赞，记录谁点了什么)
class PostLike(models.Model):
    """用户点赞记录"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes', verbose_name="帖子")
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="点赞用户")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="点赞时间")

    class Meta:
        # 核心约束：同一个用户对同一篇帖子只能有一条记录 (联合唯一)
        unique_together = ('post', 'user')
        verbose_name = "点赞记录"
        verbose_name_plural = "点赞记录"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} liked {self.post.title}"