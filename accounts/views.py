from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import DatabaseError, IntegrityError
from django.db.models import Case, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST
from .forms import PasswordSignupConflictError, PasswordSignupRetryError, RegisterForm, EmailLoginForm, RoleForm, SuspensionForm
from committees.models import CommitteeMember
from events.models import Event

from .decorators import role_required
from .forms import ProfileEditForm
from .google_auth import apply_google_login_headers, google_login_context
from .provisioning import is_identifier_conflict
from .lifecycle import apply_suspension
from .models import Profile, Role, get_role, has_minimum_role, set_role

User = get_user_model()


def register(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    form = RegisterForm(request.POST or None)
    response_status = 200
    if request.method == "POST" and form.is_valid():
        try:
            user = form.save()
        except (IntegrityError, PasswordSignupConflictError):
            # Database identity indexes can reject a race after form validation.
            form.add_error(None, "Account creation could not be completed. Try a different username or email, or sign in.")
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
@require_http_methods(["GET", "POST"])
def edit_profile(request):
    account_profile, _ = Profile.objects.get_or_create(user=request.user)
    form = ProfileEditForm(
        request.POST if request.method == "POST" else None,
        instance=request.user,
        profile=account_profile,
    )
    if request.method == "POST" and form.is_valid():
        fields = ["first_name", "last_name"]
        if not form.fields["email"].disabled:
            fields.append("email")
        try:
            form.save(commit=False).save(update_fields=fields)
            Profile.objects.filter(pk=account_profile.pk).update(
                graduation_year=form.cleaned_data["graduation_year"],
            )
        except DatabaseError as error:
            if is_identifier_conflict(error):
                form.add_error("email", "An account with this email already exists.")
            else:
                form.add_error(None, "Your changes could not be confirmed. Reload My account and try again.")
        else:
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    return render(request, "accounts/edit_profile.html", {"form": form})


@login_required
def profile(request):
    role = get_role(request.user)
    committees = CommitteeMember.objects.filter(user=request.user).select_related("committee")
    context = {"role": role, "committees": committees}
    if has_minimum_role(role, Role.MEMBER):
        attendance = Event.objects.attendance_summary_for(request.user)
        context.update(
            show_attendance=True,
            attendance_history=attendance["history"],
            attendance_total=attendance["total"],
            attendance_count=attendance["attended"],
            attendance_rate=attendance["rate"],
            attendance_since=attendance["since"],
        )
    return render(request, "accounts/profile.html", context)


@role_required(Role.ADMIN)
def user_list(request):
    profiles = Profile.objects.select_related("user").annotate(
        privilege_order=Case(
            When(user__is_superuser=True, then=Value(4)),
            When(role=Role.ADMIN, then=Value(4)),
            When(role=Role.OFFICER, then=Value(3)),
            When(role=Role.MEMBER, then=Value(2)),
            default=Value(1),
            output_field=IntegerField(),
        )
    )
    email_filter = request.GET.get("email", "").strip()
    role_filter = request.GET.get("role", "").strip()
    status_filter = request.GET.get("status", "").strip()
    if email_filter:
        profiles = profiles.filter(
            Q(user__email__icontains=email_filter) | Q(user__username__icontains=email_filter)
        )
    if role_filter in Role.values:
        profiles = profiles.filter(role=role_filter)
    if status_filter == "active":
        profiles = profiles.filter(user__is_active=True, is_suspended=False)
    elif status_filter == "suspended":
        profiles = profiles.filter(is_suspended=True)
    elif status_filter == "inactive":
        profiles = profiles.filter(user__is_active=False, is_suspended=False)
    profiles = profiles.order_by("-privilege_order", "user__username")
    total_profiles = profiles.count()
    try:
        display_limit = max(50, min(int(request.GET.get("load_more", "50")), 5000))
    except ValueError:
        display_limit = 50
    displayed_profiles = profiles[:display_limit]
    query = request.GET.copy()
    query.pop("load_more", None)
    filter_query = query.urlencode()
    return render(
        request,
        "accounts/user_list.html",
        {
            "profiles": displayed_profiles,
            "role_choices": Role.choices,
            "total_profiles": total_profiles,
            "display_limit": display_limit,
            "has_more": total_profiles > display_limit,
            "next_display_limit": display_limit + 50,
            "filter_query": filter_query,
            "filters": {
                "email": email_filter,
                "role": role_filter,
                "status": status_filter,
            },
        },
    )


@require_POST
@role_required(Role.ADMIN)
def bulk_change_roles(request):
    changed = 0
    errors = []
    for key, role in request.POST.items():
        if not key.startswith("role_"):
            continue
        pk = key.removeprefix("role_")
        target = User.objects.filter(pk=pk).first()
        if target is None:
            errors.append("One selected account no longer exists.")
            continue
        if target == request.user:
            errors.append("Your own role cannot be changed.")
            continue
        if target.is_superuser:
            errors.append("Superuser accounts always have the Admin role.")
            continue
        try:
            expected_version = int(request.POST.get(f"version_{pk}", "0"))
        except ValueError:
            errors.append("One role update had an invalid version.")
            continue
        try:
            set_role(
                target,
                role,
                actor=request.user,
                source="account_role_management",
                expected_version=expected_version,
                reconcile_rejected=True,
            )
        except (ValueError, DatabaseError) as error:
            errors.append(str(error))
        else:
            changed += 1
    if changed:
        messages.success(request, f"{changed} role change(s) saved.")
    for error in errors:
        messages.error(request, error)
    return redirect("accounts:user_list")

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
