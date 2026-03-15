from django import forms
from .models import ProblemDiscussion, CodeSubmission


# ==========================================
# 1. 讨论区表单
# ==========================================
class DiscussionForm(forms.ModelForm):
    """
    用于用户发布题目讨论或提问。
    """

    class Meta:
        model = ProblemDiscussion
        fields = ['title', 'content']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '讨论标题（例如：这题的数据范围有什么坑？）',
                'maxlength': 200
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': '请详细描述你的问题、思路或遇到的错误...',
                'cols': 40
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].label = "讨论主题"
        self.fields['content'].label = "详细内容"
        self.fields['title'].required = True
        self.fields['content'].required = True


# ==========================================
# 2. 普通用户代码提交表单
# ==========================================
class CodeSubmissionForm(forms.ModelForm):
    """
    供前端用户提交代码解题使用。
    mode 不放进前端表单里，由后端根据 session / 当前模式自动写入。
    """

    class Meta:
        model = CodeSubmission
        fields = ['problem', 'code', 'language']
        widgets = {
            'problem': forms.Select(attrs={
                'class': 'form-select'
            }),
            'code': forms.Textarea(attrs={
                'class': 'form-control font-monospace',
                'rows': 15,
                'placeholder': '# 在此编写你的代码...\n# 例如:\n# def solve():\n#     pass',
                'spellcheck': 'false'
            }),
            'language': forms.Select(attrs={
                'class': 'form-select'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['problem'].label = "选择题目"
        self.fields['code'].label = "代码内容"
        self.fields['language'].label = "编程语言"

        self.fields['problem'].required = True
        self.fields['code'].required = True
        self.fields['language'].required = True

        self.fields['code'].help_text = "请在这里输入完整的可运行代码。"
        self.fields['language'].help_text = "请选择本次提交使用的语言。"


# ==========================================
# 3. Django Admin 提交记录管理表单
# ==========================================
class CodeSubmissionAdminForm(forms.ModelForm):
    """
    专为 Django Admin 后台设计的表单。
    包含所有字段，兼容新增的 mode 字段。
    """

    class Meta:
        model = CodeSubmission
        fields = '__all__'
        widgets = {
            'code': forms.Textarea(attrs={
                'class': 'vLargeTextField font-monospace',
                'rows': 15,
                'spellcheck': 'false'
            }),
            'problem': forms.Select(attrs={
                'class': 'form-select'
            }),
            'language': forms.Select(attrs={
                'class': 'form-select'
            }),
            'mode': forms.Select(attrs={
                'class': 'form-select'
            }),
            'feedback': forms.Textarea(attrs={
                'rows': 6,
                'style': 'font-family: monospace;'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'problem' in self.fields:
            self.fields['problem'].label = "所属题目"

        if 'user' in self.fields:
            self.fields['user'].label = "提交用户"
            self.fields['user'].help_text = "提交代码的用户。"

        if 'language' in self.fields:
            self.fields['language'].label = "编程语言"

        if 'mode' in self.fields:
            self.fields['mode'].label = "作答模式"
            self.fields['mode'].help_text = "练习模式 / 考试模式。"

        if 'status' in self.fields:
            self.fields['status'].label = "判题状态"

        if 'feedback' in self.fields:
            self.fields['feedback'].label = "判题反馈"

        if 'execution_time' in self.fields:
            self.fields['execution_time'].label = "运行时间(ms)"

        if 'execution_memory' in self.fields:
            self.fields['execution_memory'].label = "运行内存(KB)"

        if 'submitted_at' in self.fields:
            self.fields['submitted_at'].label = "提交时间"
            self.fields['submitted_at'].help_text = "系统自动记录提交时间。"

        if 'code' in self.fields:
            self.fields['code'].label = "代码内容"