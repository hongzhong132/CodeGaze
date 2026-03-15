from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from .models import Profile


class ProfileUpdateForm(forms.ModelForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = Profile
        fields = ["nickname", "avatar", "bio"]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.user = user

        if user:
            self.fields["email"].initial = user.email

    def save(self, commit=True):
        profile = super().save(commit=False)

        if self.user is not None:
            self.user.email = self.cleaned_data.get("email", "")
            if commit:
                self.user.save()

        if commit:
            profile.save()

        return profile


class CustomPasswordChangeForm(PasswordChangeForm):
    pass