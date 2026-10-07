from .models import Role, get_role, has_minimum_role


def roles(request):
    """Expose the signed-in user's role to every template (for navigation)."""
    role = get_role(request.user) if hasattr(request, "user") else None
    return {
        "user_role": role,
        "is_member": has_minimum_role(role, Role.MEMBER),
        "is_officer": has_minimum_role(role, Role.OFFICER),
        "is_admin": has_minimum_role(role, Role.ADMIN),
    }
