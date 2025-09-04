from __future__ import annotations

from itertools import count
from typing import Optional, TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

User = get_user_model()

class ProjectQuerySet(models.QuerySet["Project"]):
    def owned_by(self, user: "AbstractUser"):
        return self.filter(owner=user)

    def open(self):
        return self.exclude(status="archived")

    def search(self, q: Optional[str]):
        if not q:
            return self
        return self.filter(models.Q(name__icontains=q) | models.Q(slug__icontains=q))


class Project(models.Model):
    TYPE_CHOICES = [
        ("game", "Game"),
        ("mod", "Mod"),
        ("software", "Software"),
        ("assets", "Assets"),
        ("web", "Web"),
    ]
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("paused", "Paused"),
        ("archived", "Archived"),
    ]

    # Core identity
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True, db_index=True)

    # Meta
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="draft")
    description = models.TextField(blank=True)

    # Ownership
    owner = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="owned_projects"
    )

    # Timestamps
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Managers
    objects = ProjectQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["type", "status"]),
            models.Index(fields=["owner", "status"]),
        ]
        ordering = ("-created_at",)

    # ---------- lifecycle helpers ----------
    def activate(self, *, save: bool = True):
        self.status = "active"
        self.archived_at = None
        if save:
            self.save(update_fields=["status", "archived_at", "updated_at"])

    def pause(self, *, save: bool = True):
        self.status = "paused"
        if save:
            self.save(update_fields=["status", "updated_at"])

    def archive(self, *, save: bool = True):
        self.status = "archived"
        self.archived_at = self.archived_at or timezone.now()
        if save:
            self.save(update_fields=["status", "archived_at", "updated_at"])

    def unarchive(self, *, save: bool = True):
        self.status = "active"
        self.archived_at = None
        if save:
            self.save(update_fields=["status", "archived_at", "updated_at"])

    # ---------- utils ----------
    def _generate_unique_slug(self) -> str:
        base = slugify(self.name) or "project"
        candidate = base
        for i in count(2):
            if not Project.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                return candidate
            candidate = f"{base}-{i}"

    def save(self, *args, **kwargs):
        # Ensure slug on create
        if not self.pk and not self.slug:
            self.slug = self._generate_unique_slug()

        # Keep archived_at in sync with status
        if self.status == "archived" and not self.archived_at:
            self.archived_at = timezone.now()
        if self.status != "archived" and self.archived_at is not None:
            self.archived_at = None

        super().save(*args, **kwargs)

    # ---------- presentation ----------
    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("projects:detail", kwargs={"slug": self.slug})
