from django import forms
from django.conf import settings
from django.forms import TextInput, Textarea, Select, SelectMultiple, ClearableFileInput
from .models import Asset, AssetType


# --- helpers ---------------------------------------------------------------

ACCEPT_ATTR = "image/*,video/*,audio/*,.zip,.7z,.pdf,.doc,.docx,.txt,.csv,.json,.glb,.gltf"
MAX_UPLOAD_MB = getattr(settings, "ASSET_MAX_UPLOAD_MB", 250)


def _normalize_tags(raw: str) -> str:
    """
    Lowercase, trim, de-duplicate, and normalize internal spacing.
    Output: comma+space separated.
    """
    seen = set()
    out = []
    for t in (x.strip().lower() for x in (raw or "").split(",") if x.strip()):
        t = " ".join(t.split())  # collapse internal whitespace
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return ", ".join(out)


def _validate_filesize(f):
    if getattr(f, "size", 0) > MAX_UPLOAD_MB * 1024 * 1024:
        raise forms.ValidationError(f"File exceeds {MAX_UPLOAD_MB} MB limit.")
    return f


# --- forms -----------------------------------------------------------------


class AssetCreateForm(forms.ModelForm):
    file_upload = forms.FileField(
        required=True,
        help_text="Initial file to create version 1",
        widget=ClearableFileInput(
            attrs={
                "class": "file-input file-input-bordered w-full",
                "accept": ACCEPT_ATTR,
            }
        ),
    )

    class Meta:
        model = Asset
        fields = ["title", "description", "asset_type", "tags", "projects"]
        widgets = {
            "title": TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "e.g., UI Button Pack",
                }
            ),
            "description": Textarea(
                attrs={
                    "class": "textarea textarea-bordered w-full",
                    "rows": 4,
                    "placeholder": "Short description of this asset (what it’s used for, where, etc.)",
                }
            ),
            "asset_type": Select(attrs={"class": "select select-bordered w-full"}),
            "tags": TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "sprite, ui, sfx",
                }
            ),
            "projects": SelectMultiple(
                attrs={
                    "class": "select select-bordered w-full",
                    "size": 6,
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        """
        Optional 'user' kwarg lets the view restrict selectable projects to the user's scope.
        Falls back to active/planning projects if available; otherwise leaves as default queryset.
        """
        super().__init__(*args, **kwargs)
        self.fields["projects"].required = False
        self.fields["asset_type"].initial = AssetType.OTHER

        # Narrow project choices if possible (active/planning; or member-only if user passed in)
        try:
            ProjectModel = self.fields["projects"].queryset.model  # type: ignore[attr-defined]
            qs = ProjectModel.objects.all()

            # If the Project model has 'status', prefer active/planning
            try:
                qs = qs.filter(status__in=["planning", "active"])
            except Exception:
                pass

            # If a user is provided and the Project model exposes memberships, scope to their projects
            if user is not None:
                # Heuristic: if there is a 'memberships' related name with 'user' fk, filter by membership
                try:
                    qs = qs.filter(memberships__user=user).distinct() | qs.filter(created_by=user)
                except Exception:
                    # If no memberships relation exists, keep prior qs
                    pass

            self.fields["projects"].queryset = qs.order_by("title")
        except Exception:
            # If anything goes wrong, keep Django's default queryset
            pass

    def clean_title(self):
        return " ".join((self.cleaned_data.get("title") or "").split())

    def clean_tags(self):
        return _normalize_tags(self.cleaned_data.get("tags", ""))

    def clean_file_upload(self):
        f = self.cleaned_data.get("file_upload")
        if not f:
            raise forms.ValidationError("Please select a file to upload.")
        _validate_filesize(f)
        # Basic content-type presence check (exact type is derived in storage)
        if not getattr(f, "content_type", None):
            raise forms.ValidationError("Could not determine file type.")
        return f


class VersionUploadForm(forms.Form):
    file_upload = forms.FileField(
        required=True,
        widget=ClearableFileInput(
            attrs={
                "class": "file-input file-input-bordered w-full",
                "accept": ACCEPT_ATTR,
            }
        ),
    )

    def clean_file_upload(self):
        f = self.cleaned_data.get("file_upload")
        if not f:
            raise forms.ValidationError("Please select a file to upload.")
        _validate_filesize(f)
        return f
