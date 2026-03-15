import os
import uuid
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.http import JsonResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count, Prefetch, F
from django.contrib import messages
from django.db import transaction
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.core.files.storage import default_storage

from .models import Category, Post, Comment, PostLike
from .forms import PostForm, CommentForm

# 初始化日志记录器
logger = logging.getLogger(__name__)

# ==========================================
# 首页与列表视图
# ==========================================

def category_list(request):
    """
    首页：展示所有分类及其最新帖子预览
    """
    categories = Category.objects.annotate(
        post_count=Count('posts')
    ).order_by('name')
    
    # 为每个分类预加载最新的3个帖子
    for cat in categories:
        # 使用 slice 进行数据库层面的限制，避免加载所有数据
        cat.latest_posts = cat.posts.all().select_related('author').order_by('-created_at')[:3]
    
    return render(request, 'community/category_list.html', {
        'categories': categories,
        'page_title': '社区首页'
    })

def post_list(request, category_id=None):
    """
    帖子列表页：支持分页、筛选和置顶排序
    """
    category = None
    posts_query = Post.objects.select_related('author', 'category').prefetch_related(
        Prefetch('likes', queryset=PostLike.objects.only('user_id'))
    )
    
    if category_id:
        category = get_object_or_404(Category, id=category_id)
        posts_query = posts_query.filter(category=category)
        page_title = f"{category.name} - 帖子列表"
    else:
        page_title = "全部帖子"
    
    # 【核心修改】排序：置顶优先 (is_pinned=True 排在前面)，然后按时间倒序
    posts_query = posts_query.order_by('-is_pinned', '-created_at')
    
    # 分页配置
    paginator = Paginator(posts_query, 15)  # 每页 15 条
    page_number = request.GET.get('page')
    
    try:
        posts_page = paginator.page(page_number)
    except PageNotAnInteger:
        posts_page = paginator.page(1)
    except EmptyPage:
        posts_page = paginator.page(paginator.num_pages)
    
    context = {
        'posts': posts_page,
        'category': category,
        'categories': Category.objects.all(),
        'page_title': page_title,
        'is_paginated': posts_page.has_other_pages(),
    }
    
    return render(request, 'community/post_list.html', context)

# ==========================================
# 帖子详情与交互视图
# ==========================================

def post_detail(request, post_id):
    """
    帖子详情页：处理浏览量、点赞状态判断、评论提交
    """
    post = get_object_or_404(
        Post.objects.select_related('author', 'category').prefetch_related('likes__user'),
        id=post_id
    )
    
    # 增加浏览量 (简单实现，生产环境可考虑用缓存或异步任务防刷)
    post.views += 1
    post.save(update_fields=['views'])
    
    # 判断当前用户是否已点赞
    is_liked = False
    if request.user.is_authenticated:
        # 使用 exists() 比 any() 更高效
        is_liked = post.likes.filter(user=request.user).exists()
    
    # 获取评论
    comments = post.comments.select_related('author').order_by('created_at')
    
    # 处理评论提交
    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            if request.user.is_authenticated:
                comment = form.save(commit=False)
                comment.post = post
                comment.author = request.user
                comment.save()
                messages.success(request, "评论发表成功！")
                return redirect('community:post_detail', post_id=post.id)
            else:
                messages.error(request, "请先登录后再发表评论。")
                return redirect('login') # 确保你有名为 'login' 的 URL
        else:
            messages.error(request, "评论内容不能为空或格式有误。")
    else:
        form = CommentForm()
        
    context = {
        'post': post,
        'comments': comments,
        'form': form,
        'is_liked': is_liked,
        'page_title': post.title
    }
    
    return render(request, 'community/post_detail.html', context)

@login_required
def create_post(request, category_id=None):
    """
    创建新帖子
    """
    initial_data = {}
    
    if category_id:
        category = get_object_or_404(Category, id=category_id)
        initial_data['category'] = category
    
    if request.method == 'POST':
        form = PostForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    post = form.save(commit=False)
                    post.author = request.user
                    # 如果表单中没有选择分类，且 URL 中指定了分类，则使用 URL 中的分类
                    if not post.category and category_id:
                        post.category = get_object_or_404(Category, id=category_id)
                    
                    post.save()
                
                messages.success(request, "🎉 帖子发布成功！快去看看吧。")
                return redirect('community:post_detail', post_id=post.id)
            except Exception as e:
                messages.error(request, f"发布失败：{str(e)}")
                logger.error(f"Post creation failed: {str(e)}")
        else:
            messages.error(request, "请修正表单中的错误后重新提交。")
            # 打印具体错误到控制台方便调试
            print(form.errors)
    else:
        form = PostForm(initial=initial_data)
    
    context = {
        'form': form,
        'category_id': category_id,
        'page_title': '发布新话题'
    }
    
    return render(request, 'community/create_post.html', context)

# ==========================================
# AJAX 接口视图
# ==========================================

@login_required
@require_POST
def toggle_like(request, post_id):
    """
    处理点赞/取消点赞逻辑 (AJAX)
    """
    post = get_object_or_404(Post, id=post_id)
    user = request.user
    
    try:
        with transaction.atomic():
            like_instance = PostLike.objects.filter(post=post, user=user).first()
            
            if like_instance:
                # 取消点赞
                like_instance.delete()
                Post.objects.filter(pk=post.pk).update(likes_count=F('likes_count') - 1)
                is_liked = False
                message = '已取消点赞'
            else:
                # 添加点赞
                PostLike.objects.create(post=post, user=user)
                Post.objects.filter(pk=post.pk).update(likes_count=F('likes_count') + 1)
                is_liked = True
                message = '点赞成功'
            
            post.refresh_from_db()
            
            return JsonResponse({
                'success': True,
                'likes_count': post.likes_count,
                'is_liked': is_liked,
                'message': message
            })
            
    except Exception as e:
        logger.error(f"Toggle like failed: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'操作失败：{str(e)}'
        }, status=500)

@login_required
@require_http_methods(["POST"])
def upload_image(request):
    """
    CKEditor 5 图片上传接口 (优化版)
    1. 使用 Django default_storage 保存文件 (兼容本地/云存储)
    2. 自动按日期创建文件夹
    3. 严格验证文件类型和大小
    4. 返回 CKEditor 5 标准格式
    """
    if not request.FILES.get('upload'):
        return JsonResponse({
            'uploaded': False,
            'error': {
                'message': '未检测到上传的文件。'
            }
        }, status=400)

    upload_file = request.FILES['upload']
    
    # 1. 验证文件扩展名
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    file_ext = os.path.splitext(upload_file.name)[1].lower()
    
    if file_ext not in allowed_extensions:
        return JsonResponse({
            'uploaded': False,
            'error': {
                'message': '不支持的文件格式。仅允许 JPG, PNG, GIF, WebP。'
            }
        }, status=400)
    
    # 2. 验证文件大小 (限制 5MB)
    max_size = 5 * 1024 * 1024  # 5MB
    if upload_file.size > max_size:
        return JsonResponse({
            'uploaded': False,
            'error': {
                'message': f'文件过大 ({upload_file.size / 1024 / 1024:.2f}MB)。最大允许 5MB。'
            }
        }, status=400)

    try:
        # 3. 构建保存路径 (按日期分文件夹: uploads/2026/03/08/)
        # 使用 default_storage 会自动处理路径分隔符 (/ 或 \)
        date_path = timezone.now().strftime('uploads/%Y/%m/%d/')
        filename = f"{uuid.uuid4().hex}{file_ext}"
        file_path = os.path.join(date_path, filename)
        
        # 4. 保存文件 (核心修复：使用 default_storage 代替 open())
        saved_name = default_storage.save(file_path, upload_file)
        
        # 5. 获取公开访问 URL
        file_url = default_storage.url(saved_name)
        
        # 6. 返回 CKEditor 5 需要的标准格式
        return JsonResponse({
            'uploaded': True,
            'url': file_url,
            'fileName': filename
        })
        
    except Exception as e:
        logger.error(f"Image upload failed: {str(e)}", exc_info=True)
        return JsonResponse({
            'uploaded': False,
            'error': {
                'message': f'服务器内部错误：{str(e)}'
            }
        }, status=500)