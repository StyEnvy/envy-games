from django.db import models, transaction
from django.contrib.auth import get_user_model
User = get_user_model()

class Asset(models.Model):
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="assets")
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=60)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("project", "name")]

class AssetVersion(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="versions")
    file = models.FileField(upload_to="assets/%Y/%m/")
    size_bytes = models.BigIntegerField()
    checksum_sha256 = models.CharField(max_length=64)
    notes = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_primary = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_primary:
            self.asset.versions.exclude(id=self.id).filter(is_primary=True).update(is_primary=False)
