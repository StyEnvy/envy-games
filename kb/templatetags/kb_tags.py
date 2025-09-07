from django import template
from django.utils.safestring import mark_safe
from django.db import models
import markdown as md

register = template.Library()


@register.filter
def markdown(value):
    """Convert markdown to HTML."""
    extensions = ['extra', 'codehilite', 'toc', 'tables', 'fenced_code']
    return mark_safe(md.markdown(value, extensions=extensions))


@register.simple_tag
def kb_stats():
    """Get KB statistics for dashboard."""
    from kb.models import Article
    return {
        'total_articles': Article.objects.filter(status='published').count(),
        'total_views': Article.objects.filter(status='published').aggregate(
            total=models.Sum('views_count'))['total'] or 0,
        'draft_articles': Article.objects.filter(status='draft').count(),
    }