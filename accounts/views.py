from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from committees.models import CommitteeMember

from .decorators import role_required
from .forms import EmailLoginForm, RegisterForm, RoleForm
from .models import Profile, Role, get_role, set_role

User = get_user_model()


def register(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created. You can now apply for membership.")
        return redirect("core:dashboard")
    return render(request, "accounts/register.html", {"form": form})


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True


@login_required
def profile(request):
    committees = CommitteeMember.objects.filter(user=request.user).select_related("committee")
    return render(
        request,
        "accounts/profile.html",
        {"role": get_role(request.user), "committees": committees},
    )


@role_required(Role.ADMIN)
def user_list(request):
    profiles = Profile.objects.select_related("user").order_by("user__username")
    return render(
        request,
        "accounts/user_list.html",
        {"profiles": profiles, "role_choices": Role.choices},
    )


@require_POST
@role_required(Role.ADMIN)
def change_role(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target == request.user:
        # Prevents an admin from accidentally locking themselves out.
        messages.error(request, "You cannot change your own role.")
        return redirect("accounts:user_list")
    form = RoleForm(request.POST)
    if form.is_valid():
        set_role(target, form.cleaned_data["role"])
        messages.success(request, f"{target.email} is now {form.cleaned_data['role']}.")
    else:
        messages.error(request, "Invalid role.")
    return redirect("accounts:user_list")
