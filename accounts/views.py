from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from committees.models import CommitteeMember

from .decorators import role_required
from .forms import EmailLoginForm, RegisterForm, RoleForm
from .google_auth import apply_google_login_headers, google_login_context
from .models import Profile, Role, get_role, set_role

User = get_user_model()


def register(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = form.save()
        except IntegrityError:
            # A username can be claimed after form validation but before save.
            # Email/case-folded uniqueness still needs a separate schema change.
            form.add_error(None, "Account creation could not be completed. Try a different username or sign in.")
        else:
            # The account stays switched off until an officer approves the
            # application, so don't sign in yet.
            messages.success(
                request,
                f"Thanks, {user.username}! Your application was submitted. "
                "You can sign in once an officer approves it.",
            )
            return redirect("core:home")
    context = {"form": form, **google_login_context(request)}
    response = render(request, "accounts/register.html", context)
    if context.get("google_enabled"):
        apply_google_login_headers(request, response)
    return response


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(google_login_context(self.request))
        return context

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        if context.get("google_enabled"):
            apply_google_login_headers(self.request, response)
        return response


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
    if target.is_superuser:
        messages.error(request, "Superuser accounts always have the Admin role.")
        return redirect("accounts:user_list")
    form = RoleForm(request.POST)
    if form.is_valid():
        set_role(target, form.cleaned_data["role"])
        messages.success(request, f"{target.email} is now {form.cleaned_data['role']}.")
    else:
        messages.error(request, "Invalid role.")
    return redirect("accounts:user_list")
