from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Article, ArticleVersion


@receiver(pre_save, sender=Article)
def auto_publish_date(sender, instance, **kwargs):
    """Automatically set published_at when status changes to published."""
    if instance.status == 'published' and not instance.published_at:
        from django.utils import timezone
        instance.published_at = timezone.now()


@receiver(post_save, sender=Article)
def create_version_on_save(sender, instance, created, **kwargs):
    """Create a version snapshot when article content changes."""
    if not created:
        # Check if content changed
        last_version = instance.versions.first()
        if last_version and last_version.content != instance.content:
            ArticleVersion.objects.create(
                article=instance,
                version_number=(last_version.version_number + 1),
                title=instance.title,
                content=instance.content,
                summary=instance.summary,
                edited_by=getattr(instance, '_current_user', instance.author),
                change_notes=getattr(instance, '_change_notes', '')
            )