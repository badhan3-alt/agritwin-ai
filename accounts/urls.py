from django.urls import path
from . import views

app_name = "accounts"
urlpatterns = [
    path("", views.profile, name="profile"),
    path("signup/", views.signup, name="signup"),
    path("login/", views.SignInView.as_view(), name="login"),
    path("logout/", views.signout, name="logout"),
    path("password/", views.ChangePasswordView.as_view(), name="password_change"),
]
