from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import RegisterForm
from .models import User

ROLE_HOME = {
    User.Role.STUDENT: "portal:student_dashboard",
    User.Role.RECRUITER: "portal:recruiter_dashboard",
    User.Role.ADMIN: "portal:admin_dashboard",
}


def home(request):
    if request.user.is_authenticated:
        return redirect("portal:dashboard")
    return render(request, "portal/home.html")


@login_required
def dashboard(request):
    """Send each user to the portal for their role."""
    return redirect(ROLE_HOME[request.user.role])


def register(request):
    if request.user.is_authenticated:
        return redirect("portal:dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f"Welcome, {user.display_name}! Your account is ready.")
        return redirect("portal:dashboard")
    return render(request, "portal/register.html", {"form": form})
