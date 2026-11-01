from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm


def style_fields(form):
    for field in form.fields.values():
        field.widget.attrs.setdefault("class", "form-control")


class SignUpForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)
        self.fields["username"].widget.attrs["autocomplete"] = "username"


class SignInForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)


class ChangePasswordForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)
