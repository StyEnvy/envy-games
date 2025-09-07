from django.db.models import Q
from .models import Article


def search_articles(query, user=None):
    """
    Search articles by title, content, tags, etc.
    """
    if not query:
        return Article.objects.none()
    
    queryset = Article.objects.filter(status='published')
    
    # Build search query
    search_terms = query.split()
    search_query = Q()
    
    for term in search_terms:
        search_query |= (
            Q(title__icontains=term) |
            Q(summary__icontains=term) |
            Q(content__icontains=term) |
            Q(tags__icontains=term)
        )
    
    return queryset.filter(search_query).distinct()