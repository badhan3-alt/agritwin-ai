from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST, require_http_methods

from farms.models import Farm
from .forms import ChangePasswordForm, SignInForm, SignUpForm


def claim_guest_farms(user, guest_session):
    """Capture the pre-login key: Django rotates the session during sign-in."""
    if guest_session:
        return Farm.objects.filter(owner__isnull=True, owner_session=guest_session).update(owner=user, owner_session="")
    return 0


def safe_next(request):
    target = request.POST.get("next", request.GET.get("next", ""))
    if target and url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
        return target
    return reverse("farms:list")


class SignInView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = SignInForm
    redirect_authenticated_user = True
    extra_context = {"active_page": "account"}

    def form_valid(self, form):
        guest_session = self.request.session.session_key
        response = super().form_valid(form)
        if claim_guest_farms(form.get_user(), guest_session):
            messages.success(self.request, _("Your farms are linked to your account."))
        return response


@sensitive_post_parameters("password1", "password2")
@never_cache
@require_http_methods(["GET", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")
    form = SignUpForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        guest_session = request.session.session_key
        with transaction.atomic():
            user = form.save()
            claim_guest_farms(user, guest_session)
        login(request, user)
        messages.success(request, _("Your account is ready. Sign in on another device to access your farms."))
        return redirect(safe_next(request))
    return render(request, "accounts/signup.html", {"form": form, "next": safe_next(request), "active_page": "account"})


@never_cache
@login_required
def profile(request):
    return render(request, "accounts/profile.html", {"active_page": "account"})


@require_POST
def signout(request):
    language = request.session.get("language")
    logout(request)
    if language in {"bn", "en"}:
        request.session["language"] = language
    messages.success(request, _("You have signed out."))
    return redirect("core:home")


class ChangePasswordView(PasswordChangeView):
    form_class = ChangePasswordForm
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:profile")
    extra_context = {"active_page": "account"}

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("Your password has been changed."))
        return response
