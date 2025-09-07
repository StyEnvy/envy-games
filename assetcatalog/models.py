# models.py
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify


class AssetType(models.TextChoices):
    IMAGE = "image", "Image"
    VIDEO = "video", "Video"
    AUDIO = "audio", "Audio"
    MODEL_3D = "model_3d", "3D Model"
    DOCUMENT = "document", "Document"
    ARCHIVE = "archive", "Archive"
    OTHER = "other", "Other"


def unique_slugify(instance, base_value, slug_field_name="slug", max_len=60):
    base_slug = slugify(base_value)[:max_len] or "asset"
    slug = base_slug
    n = 2
    Model = instance.__class__
    while Model.objects.filter(**{slug_field_name: slug}).exclude(pk=instance.pk).exists():
        suffix = f"-{n}"
        slug = f"{base_slug[: max_len - len(suffix)]}{suffix}"
        n += 1
    return slug


class Asset(models.Model):
    """
    Logical asset record (title/metadata), with immutable version rows.
    current_version points at the latest version.
    """
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True, db_index=True)
    description = models.TextField(blank=True)
    asset_type = models.CharField(max_length=20, choices=AssetType.choices, default=AssetType.OTHER)
    tags = models.CharField(max_length=300, blank=True, help_text="Comma-separated tags")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assets_created")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    # Linkage to Projects (many-to-many via explicit through)
    projects = models.ManyToManyField("projects.Project", through="AssetProject", related_name="assets")

    # Points at latest version for quick access (nullable until first version is added)
    current_version = models.ForeignKey(
        "AssetVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at", "title"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["created_by", "created_at"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.title)
        super().save(*args, **kwargs)

    @property
    def tag_list(self):
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def classify_asset_type(self, content_type: str) -> str:
        c = (content_type or "").lower()
        if c.startswith("image/"):
            return AssetType.IMAGE
        if c.startswith("video/"):
            return AssetType.VIDEO
        if c.startswith("audio/"):
            return AssetType.AUDIO
        if c in {"application/zip", "application/x-7z-compressed"}:
            return AssetType.ARCHIVE
        if c in {
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }:
            return AssetType.DOCUMENT
        return AssetType.OTHER

    def add_version(self, uploaded_file, *, user):
        from django.db.models import Max
        from .storage import store_blob

        with transaction.atomic():
            meta = store_blob(uploaded_file)
            latest = self.versions.select_for_update().aggregate(m=Max("number"))["m"] or 0
            number = latest + 1
            av = AssetVersion.objects.create(
                asset=self,
                number=number,
                original_filename=getattr(uploaded_file, "name", f"{self.slug}-v{number}"),
                content_type=meta["content_type"],
                size_bytes=meta["size_bytes"],
                sha256=meta["sha256"],
                blob_path=meta["blob_path"],
                uploaded_by=user,
            )
            # Auto-classify on first upload or if still OTHER
            if not self.current_version or self.asset_type == AssetType.OTHER:
                at = self.classify_asset_type(av.content_type)
                if at != self.asset_type:
                    self.asset_type = at
            self.current_version = av
            self.save(update_fields=["current_version", "asset_type"])
            return av

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("assetcatalog:detail", kwargs={"slug": self.slug})


class AssetVersion(models.Model):
    """
    A single immutable file version stored in blob storage under MEDIA_ROOT.
    We store metadata + a blob_path (CharField) pointing to the content-addressed file.
    """
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField(help_text="Monotonic version number (1..N)")
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=150, db_index=True)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)
    blob_path = models.CharField(max_length=255, help_text="Relative path under MEDIA_ROOT to content blob")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="asset_uploads")

    class Meta:
        ordering = ["-created_at", "-number"]
        constraints = [
            models.UniqueConstraint(fields=["asset", "number"], name="asset_version_unique_number_per_asset"),
        ]
        indexes = [
            models.Index(fields=["sha256"]),
            models.Index(fields=["content_type"]),
        ]

    def __str__(self):
        return f"{self.asset.title} v{self.number}"

    @property
    def is_image(self) -> bool:
        return (self.content_type or "").startswith("image/")

    @property
    def filename(self) -> str:
        return self.original_filename


class AssetProject(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="asset_project_links")
    added_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["asset", "project"], name="assetproject_unique_asset_project"),
        ]
        ordering = ["-added_at"]

    def __str__(self):
        return f"{self.asset} ↔ {self.project}"
