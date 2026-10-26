from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import DatabaseError, IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .forms import PasswordSignupRetryError, RegisterForm, EmailLoginForm, RoleForm, SuspensionForm
from committees.models import CommitteeMember

from .decorators import role_required
from .google_auth import apply_google_login_headers, google_login_context
from .lifecycle import apply_suspension
from .models import Profile, Role, get_role, set_role

User = get_user_model()


def register(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    form = RegisterForm(request.POST or None)
    response_status = 200
    if request.method == "POST" and form.is_valid():
        try:
            user = form.save()
        except IntegrityError:
            # A username can be claimed after form validation but before save.
            # Email/case-folded uniqueness still needs a separate schema change.
            form.add_error(None, "Account creation could not be completed. Try a different username or sign in.")
        except PasswordSignupRetryError as error:
            form.add_error(None, str(error))
            response_status = 503
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
    response = render(request, "accounts/register.html", context, status=response_status)
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

        # Prevents an admin from accidentally locking themselves out.

@require_POST
@role_required(Role.ADMIN)
def change_role(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target == request.user:
        messages.error(request, "You cannot change your own role.")
        return redirect("accounts:user_list")
    if target.is_superuser:
        messages.error(request, "Superuser accounts always have the Admin role.")
        return redirect("accounts:user_list")
    form = RoleForm(request.POST)
    if form.is_valid():
        try:
            set_role(
                target, form.cleaned_data["role"], actor=request.user,
                source="account_role_management", expected_version=form.cleaned_data["version"],
                reconcile_rejected=True,
            )
        except ValueError as error:
            messages.error(request, str(error))
        except DatabaseError:
            messages.error(request, "The role change could not be confirmed. Reload the users page before trying again.")
        else:
            messages.success(request, f"{target.email} is now {form.cleaned_data['role']}.")
    else:
        messages.error(request, "Invalid role.")
    return redirect("accounts:user_list")


@require_POST
@role_required(Role.ADMIN)
def change_suspension(request, pk):
    """Preserve prior activation and complete recorded review access safely."""
    target = get_object_or_404(User, pk=pk)

    if target == request.user or target.is_superuser:
        messages.error(request, "This account cannot be suspended or reinstated here.")
        return redirect("accounts:user_list")

    form = SuspensionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid suspension action.")
        return redirect("accounts:user_list")

    action = form.cleaned_data["action"]
    try:
        apply_suspension(target, action == "suspend", expected_version=form.cleaned_data["version"])
    except ValueError as error:
        messages.error(request, str(error))
    except DatabaseError:
        messages.error(request, "The account access update could not be confirmed. Reload the users page and retry the pending action.")
    else:
        if action == "suspend":
            messages.success(request, f"{target.email or target.username} suspended.")
        else:
            messages.success(request, f"Suspension removed for {target.email or target.username}.")

    return redirect("accounts:user_list")
