"""Shared resource library with the same effective-account guards as notices."""

from django.contrib import messages
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import Role, has_minimum_role
from .forms import ResourceForm
from .models import Resource
from .permissions import announcement_access


@announcement_access(Role.MEMBER)
def resource_list(request):
    query = request.GET.get("q", "").strip()[:100]
    category = request.GET.get("category", "").strip()[:64]
    tag = request.GET.get("tag", "").strip().casefold()
    resources = Resource.objects.all()
    if query:
        resources = resources.filter(Q(title__icontains=query) | Q(description__icontains=query))
    if category:
        resources = resources.filter(category=category)
    if tag:
        resources = resources.filter(tags__contains=[tag])
    categories = sorted(set(Resource.objects.exclude(category="").values_list("category", flat=True)))
    return render(request, "announcements/resource_list.html", {
        "resources": resources, "categories": categories, "query": query,
        "selected_category": category, "selected_tag": tag,
        "can_manage": has_minimum_role(request.announcement_role, Role.OFFICER),
    })


@require_http_methods(["GET", "POST"])
@announcement_access(Role.OFFICER)
def resource_edit(request, pk=None):
    resource = get_object_or_404(Resource, pk=pk) if pk else Resource(created_by=request.user)
    form = ResourceForm(request.POST if request.method == "POST" else None,
                        request.FILES if request.method == "POST" else None, instance=resource)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Resource saved.")
        return redirect("resources:list")
    return render(request, "announcements/resource_form.html", {"form": form, "resource": resource})


@require_http_methods(["GET", "POST"])
@announcement_access(Role.OFFICER)
def resource_delete(request, pk):
    resource = get_object_or_404(Resource, pk=pk)
    if request.method == "POST":
        # File bytes are retained for a separate, deliberate retention policy.
        # The private download route no longer resolves a removed record.
        resource.delete()
        messages.success(request, "Resource removed from the library.")
        return redirect("resources:list")
    return render(request, "announcements/confirm_delete.html", {
        "object": resource, "kind": "resource", "cancel_url": "resources:list",
    })


@announcement_access(Role.MEMBER)
def resource_open(request, pk):
    resource = get_object_or_404(Resource, pk=pk)
    if resource.url:
        # Validate again for records inserted outside the web form. Never fetch
        # external URLs on the server or redirect to a non-HTTP scheme.
        from django.core.validators import URLValidator
        from django.core.exceptions import ValidationError
        try:
            URLValidator(schemes=["http", "https"])(resource.url)
        except ValidationError:
            raise Http404("This resource link is invalid.") from None
        response = redirect(resource.url)
        response["Referrer-Policy"] = "no-referrer"
    else:
        try:
            stream = resource.file.open("rb")
        except (ValueError, OSError):
            raise Http404("This resource file is unavailable.") from None
        response = FileResponse(stream, as_attachment=True, filename=resource.file.name.rsplit("/", 1)[-1],
                                content_type="application/octet-stream")
        response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response
