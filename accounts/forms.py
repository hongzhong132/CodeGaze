from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import UserProfile

User = get_user_model()


class RegisterForm(forms.Form):
    email = forms.EmailField(
        label="邮箱",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "请输入邮箱",
            }
        ),
    )
    username = forms.CharField(
        label="账号",
        min_length=3,
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "请输入账号",
            }
        ),
    )
    password1 = forms.CharField(
        label="密码",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "请输入密码",
            }
        ),
    )
    password2 = forms.CharField(
        label="确认密码",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "请再次输入密码",
            }
        ),
    )

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("该邮箱已被注册。")
        return email

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("该账号已存在，请更换。")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "两次输入的密码不一致。")

        if password1:
            try:
                validate_password(password1)
            except DjangoValidationError as e:
                self.add_error("password1", e)

        return cleaned_data


class ProfileUpdateForm(forms.ModelForm):
    email = forms.EmailField(required=False, label="邮箱")

    class Meta:
        model = UserProfile
        fields = [
            "avatar",
            "nickname",
            "bio",
            "real_name",
            "student_no",
            "teacher_no",
        ]
        labels = {
            "avatar": "头像",
            "nickname": "昵称",
            "bio": "个性签名 / 简介",
            "real_name": "真实姓名",
            "student_no": "学号",
            "teacher_no": "工号",
        }
        widgets = {
            "nickname": forms.TextInput(attrs={"placeholder": "请输入你的昵称"}),
            "bio": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "写一点关于你自己的内容，比如擅长语言、学习目标、研究兴趣等……",
                }
            ),
            "real_name": forms.TextInput(attrs={"placeholder": "请输入真实姓名"}),
            "student_no": forms.TextInput(attrs={"placeholder": "请输入学号"}),
            "teacher_no": forms.TextInput(attrs={"placeholder": "请输入工号"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.user = user

        if user is not None:
            self.fields["email"].initial = getattr(user, "email", "")

        role = None
        if self.instance and getattr(self.instance, "role", None):
            role = self.instance.role

        if role == "teacher":
            self.fields["student_no"].widget = forms.HiddenInput()
            self.fields["student_no"].required = False
            self.fields["teacher_no"].required = False
        else:
            self.fields["teacher_no"].widget = forms.HiddenInput()
            self.fields["teacher_no"].required = False
            self.fields["student_no"].required = False

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar:
            max_size = 5 * 1024 * 1024
            if avatar.size > max_size:
                raise forms.ValidationError("头像图片不能超过 5MB。")

            valid_types = ["image/jpeg", "image/png", "image/webp", "image/gif"]
            if hasattr(avatar, "content_type") and avatar.content_type not in valid_types:
                raise forms.ValidationError("仅支持 JPG、PNG、WEBP、GIF 格式图片。")
        return avatar

    def clean_nickname(self):
        nickname = self.cleaned_data.get("nickname", "").strip()
        return nickname

    def clean_bio(self):
        bio = self.cleaned_data.get("bio", "").strip()
        return bio

    def save(self, commit=True):
        profile = super().save(commit=False)

        if self.user is not None:
            self.user.email = self.cleaned_data.get("email", "").strip()
            if commit:
                self.user.save(update_fields=["email"])

        if commit:
            profile.save()

        return profile


class CustomPasswordChangeForm(PasswordChangeForm):
    pass