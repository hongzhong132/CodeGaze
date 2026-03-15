# community/forms.py
from django import forms
from .models import Post, Comment

class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['category', 'title', 'content']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': '请输入一个吸引人的标题...',
                'style': 'font-weight: 500;'
            }),
            'category': forms.Select(attrs={
                'class': 'form-select',
                'aria-label': '选择帖子分类'
            }),
            # ✅ 重新加上 display: none; - 让 CKEditor 接管显示
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': '5',
                'id': 'id_content', 
                'placeholder': '分享你的想法...',
                'style': 'min-height: 400px; display: none;'  # ← 关键！让 JS 隐藏它
            }),
        }

    def clean_title(self):
        title = self.cleaned_data.get('title')
        if len(title) < 5:
            raise forms.ValidationError("标题太短了。")
        return title

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3, 
                'placeholder': '写下你的回复...',
                'style': 'resize: vertical; min-height: 80px;'
            }),
        }
    
    def clean_content(self):
        content = self.cleaned_data.get('content')
        if not content or len(content.strip()) == 0:
            raise forms.ValidationError("评论不能为空。")
        return content