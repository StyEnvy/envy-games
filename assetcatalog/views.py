from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseNotModified
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import ListView, DetailView, CreateView, View
from django.db.models import Q

from accounts.views import RoleRequiredMixin
from accounts.models import UserRole

from .forms import AssetCreateForm, VersionUploadForm
from .models import Asset, AssetVersion, AssetType
from .storage import ensure_image_thumbnail, _storage

import logging

logger = logging.getLogger(__name__)

PM_OR_DEV = (UserRole.PROJECT_MANAGER, UserRole.DEVELOPER)

# Toggle to require users to be on at least one linked project to download
REQUIRE_MEMBERSHIP = getattr(settings, "ASSET_REQUIRE_PROJECT_MEMBERSHIP", False)


class AssetRoleGuard(RoleRequiredMixin):
    required_roles = PM_OR_DEV


def _user_can_access_asset(user, asset: Asset) -> bool:
    """
    Optional project-scoped visibility check.
    Keeps soft dependency on your ProjectMembership relation if present.
    """
    if not REQUIRE_MEMBERSHIP:
        return True
    try:
        # If there's a memberships relation (projects.ProjectMembership with user FK)
        return asset.projects.filter(memberships__user=user).exists() or asset.created_by_id == user.id
    except Exception:
        # If membership model isn't wired, fail open (or set REQUIRE_MEMBERSHIP=True only when available)
        return True


class AssetListView(AssetRoleGuard, ListView):
    model = Asset
    template_name = "assetcatalog/asset_list.html"
    context_object_name = "assets"
    paginate_by = 20  # default

    SORT_ALLOWLIST = {"created_at", "-created_at", "title", "-title"}
    SORT_LABELS = {
        "-created_at": "Newest first",
        "created_at": "Oldest first",
        "title": "Title A–Z",
        "-title": "Title Z–A",
    }
    PER_CHOICES = (12, 24, 48, 96)

    def get_paginate_by(self, queryset):
        try:
            per = int(self.request.GET.get("per", self.paginate_by))
        except (TypeError, ValueError):
            per = self.paginate_by
        return max(6, min(per, 96))

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("current_version", "created_by")
            .prefetch_related("projects")
        )
        q = (self.request.GET.get("q") or "").strip()
        kind = (self.request.GET.get("type") or "").strip()
        project_id = (self.request.GET.get("project") or "").strip()

        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(description__icontains=q)
                | Q(tags__icontains=q)
                | Q(slug__icontains=q)
            )
        if kind and kind in dict(AssetType.choices):
            qs = qs.filter(asset_type=kind)
        if project_id.isdigit():
            qs = qs.filter(projects__id=int(project_id))

        sort = (self.request.GET.get("sort") or "-created_at").strip()
        if sort not in self.SORT_ALLOWLIST:
            sort = "-created_at"
        self._current_sort = sort  # stash for context
        return qs.order_by(sort).distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # inputs
        st = (self.request.GET.get("type") or "")
        ctx["q"] = self.request.GET.get("q", "")
        ctx["selected_type"] = st
        ctx["project"] = self.request.GET.get("project", "")

        # type options (already comparison-free)
        ctx["asset_types_annot"] = [(val, label, (val == st)) for val, label in AssetType.choices]

        # sort options (comparison-free in template)
        sort = getattr(self, "_current_sort", "-created_at")
        ctx["sort"] = sort
        ctx["sort_options"] = [(val, self.SORT_LABELS[val], val == sort) for val in (
            "-created_at", "created_at", "title", "-title"
        )]

        # per-page options (comparison-free)
        per = self.get_paginate_by(self.object_list)
        ctx["per"] = per
        ctx["per_options"] = [(n, str(n), n == per) for n in self.PER_CHOICES]

        # persistent querystring for pagination (minus 'page')
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()

        # flag for UI
        ctx["has_filters"] = bool(ctx["q"] or ctx["selected_type"] or self.request.GET.get("sort") or self.request.GET.get("per"))
        return ctx

class AssetDetailView(AssetRoleGuard, DetailView):
    model = Asset
    slug_field = "slug"
    slug_url_kwarg = "slug"
    template_name = "assetcatalog/asset_detail.html"
    context_object_name = "asset"

    DEFAULT_VERSION_LIMIT = 25

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        vlimit = self._version_limit()
        versions_qs = self.object.versions.select_related("uploaded_by").order_by("-number")
        ctx["versions"] = versions_qs[:vlimit]
        ctx["more_versions"] = versions_qs.count() > vlimit
        ctx["upload_form"] = VersionUploadForm()

        thumb = None
        v = self.object.current_version
        if v and v.is_image:
            try:
                thumb = ensure_image_thumbnail(v.sha256, v.blob_path)
            except Exception as e:
                logger.warning("Thumbnail generation failed for %s v%s: %s", self.object.slug, v.number, e)
                thumb = None
        ctx["thumb_rel"] = thumb

        return ctx

    def _version_limit(self) -> int:
        # Allow ?limit= to override, clamped
        try:
            v = int(self.request.GET.get("limit", self.DEFAULT_VERSION_LIMIT))
        except (TypeError, ValueError):
            v = self.DEFAULT_VERSION_LIMIT
        return max(5, min(v, 200))


class AssetCreateView(AssetRoleGuard, CreateView):
    model = Asset
    form_class = AssetCreateForm
    template_name = "assetcatalog/asset_form.html"

    def get_success_url(self):
        return self.object.get_absolute_url()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Let the form scope project choices to the user
        kwargs["user"] = getattr(self.request, "user", None)
        return kwargs

    def get_initial(self):
        init = super().get_initial()
        # Allow pre-selecting type/project via query params
        kind = (self.request.GET.get("type") or "").strip()
        if kind in dict(AssetType.choices):
            init["asset_type"] = kind
        proj = (self.request.GET.get("project") or "").strip()
        if proj.isdigit():
            init["projects"] = [int(proj)]
        return init

    def form_valid(self, form):
        from django.shortcuts import redirect
        form.instance.created_by = self.request.user
        with transaction.atomic():
            # Save the Asset without M2M so we can populate the through model
            self.object = form.save(commit=False)
            self.object.save()

            # Attach selected projects, recording who added the link
            projects = form.cleaned_data.get("projects") or []
            self.object.projects.set(projects, through_defaults={"added_by": self.request.user})

            # Create initial version
            self.object.add_version(form.cleaned_data["file_upload"], user=self.request.user)

        messages.success(self.request, "Asset created with version 1.")
        return redirect(self.get_success_url())


class UploadVersionView(AssetRoleGuard, View):
    def post(self, request, slug):
        asset = get_object_or_404(Asset, slug=slug)
        form = VersionUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "Please choose a file to upload.")
            return redirect("assetcatalog:detail", slug=slug)

        av = asset.add_version(form.cleaned_data["file_upload"], user=request.user)
        messages.success(request, f"Uploaded version {av.number}.")
        # optional ?next= to bounce back to the list after upload
        nxt = request.POST.get("next") or request.GET.get("next")
        return redirect(nxt or asset.get_absolute_url())


class DownloadVersionView(AssetRoleGuard, View):
    def head(self, request, version_id):
        """
        Support HEAD so clients can quickly inspect headers.
        """
        v = get_object_or_404(AssetVersion, id=version_id)
        if not _user_can_access_asset(request.user, v.asset):
            raise Http404()
        if not _storage.exists(v.blob_path):
            raise Http404("File not found")
        # Return headers only; no body
        resp = FileResponse(b"", content_type=v.content_type or "application/octet-stream")
        self._apply_common_headers(resp, v)
        return resp

    def get(self, request, version_id):
        v = get_object_or_404(AssetVersion, id=version_id)
        if not _user_can_access_asset(request.user, v.asset):
            raise Http404()

        # Conditional request via ETag
        inm = request.META.get("HTTP_IF_NONE_MATCH")
        if inm and v.sha256 in self._parse_ims_etags(inm):
            return HttpResponseNotModified()

        if not _storage.exists(v.blob_path):
            raise Http404("File not found")

        f = _storage.open(v.blob_path, "rb")
        resp = FileResponse(f, content_type=v.content_type or "application/octet-stream")
        self._apply_common_headers(resp, v)
        return resp

    @staticmethod
    def _apply_common_headers(resp, v: AssetVersion):
        resp["Content-Disposition"] = f'attachment; filename="{v.original_filename}"'
        resp["ETag"] = v.sha256
        resp["Cache-Control"] = "private, max-age=31536000, immutable"
        # Hint support for resumable downloads if your front proxy handles ranges
        resp["Accept-Ranges"] = "bytes"

    @staticmethod
    def _parse_ims_etags(header_val: str):
        # Parses ETag list from If-None-Match header; handles tokens with/without quotes
        etags = []
        for part in header_val.split(","):
            t = part.strip()
            if t.startswith("W/"):
                t = t[2:]
            if t.startswith('"') and t.endswith('"'):
                t = t[1:-1]
            if t:
                etags.append(t)
        return etags
