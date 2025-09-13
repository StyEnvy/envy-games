from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q, Count, F, Prefetch
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
)
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_page

from .models import (
    Article, Category, ArticleVersion, ArticleImage, 
    ArticleAttachment, ArticleFeedback, ArticleLink
)
from .forms import (
    ArticleForm, CategoryForm, ArticleImageForm, 
    ArticleAttachmentForm, ArticleLinkForm, ArticleFeedbackForm
)
from .utils import render_markdown, extract_headings, normalize_tags

import json
import logging

logger = logging.getLogger(__name__)


class KBHomeView(LoginRequiredMixin, TemplateView):
    """Knowledge Base home page with featured articles and categories"""
    template_name = 'kb/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Featured articles
        context['featured_articles'] = Article.objects.filter(
            status='published',
            is_featured=True
        ).select_related('author', 'category')[:6]
        
        # Recent articles
        context['recent_articles'] = Article.objects.filter(
            status='published'
        ).select_related('author', 'category')[:10]
        
        # Popular articles
        context['popular_articles'] = Article.objects.filter(
            status='published'
        ).select_related('author', 'category').order_by('-views_count')[:10]
        
        # Categories with article counts
        context['categories'] = Category.objects.filter(
            is_active=True
        ).annotate(
            article_count=Count('articles', filter=Q(articles__status='published'))
        ).order_by('position', 'name')
        
        # Statistics
        context['stats'] = {
            'total_articles': Article.objects.filter(status='published').count(),
            'total_categories': Category.objects.filter(is_active=True).count(),
            'total_views': Article.objects.filter(
                status='published'
            ).aggregate(total=Count('views_count'))['total'] or 0,
        }
        
        # User's recent drafts
        if self.request.user.is_authenticated:
            context['my_drafts'] = Article.objects.filter(
                author=self.request.user,
                status='draft'
            ).select_related('category')[:5]
        
        return context


class ArticleListView(LoginRequiredMixin, ListView):
    """List and search articles with filtering"""
    model = Article
    template_name = 'kb/article_list.html'
    context_object_name = 'articles'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Article.objects.select_related(
            'author', 'category'
        ).prefetch_related('images')
        
        # Status filter
        status = self.request.GET.get('status', 'published')
        if status == 'my_drafts':
            queryset = queryset.filter(
                author=self.request.user,
                status='draft'
            )
        elif status == 'all' and self.request.user.is_staff:
            # Staff can see all articles
            pass
        else:
            queryset = queryset.filter(status='published')
        
        # Search query
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(title__icontains=q) |
                Q(summary__icontains=q) |
                Q(content__icontains=q) |
                Q(tags__icontains=q) |
                Q(category__name__icontains=q)
            ).distinct()
        
        # Category filter
        category_slug = self.request.GET.get('category')
        if category_slug:
            try:
                category = Category.objects.get(slug=category_slug, is_active=True)
                # Include subcategories
                categories = [category] + category.get_descendants()
                queryset = queryset.filter(category__in=categories)
            except Category.DoesNotExist:
                pass
        
        # Tag filter
        tag = self.request.GET.get('tag')
        if tag:
            queryset = queryset.filter(tags__icontains=tag)
        
        # Difficulty filter
        difficulty = self.request.GET.get('difficulty')
        if difficulty in ['beginner', 'intermediate', 'advanced']:
            queryset = queryset.filter(difficulty=difficulty)
        
        # Featured filter
        if self.request.GET.get('featured'):
            queryset = queryset.filter(is_featured=True)
        
        # Sorting
        sort = self.request.GET.get('sort', '-published_at')
        sort_options = {
            'title': 'title',
            '-title': '-title',
            'views': '-views_count',
            'helpful': '-helpful_count',
            'newest': '-published_at',
            'oldest': 'published_at',
            'updated': '-updated_at',
        }
        if sort in sort_options:
            queryset = queryset.order_by(sort_options[sort])
        else:
            queryset = queryset.order_by('-is_pinned', '-published_at')
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Categories for sidebar
        context['categories'] = Category.objects.filter(
            is_active=True,
            parent__isnull=True
        ).annotate(
            article_count=Count('articles', filter=Q(articles__status='published'))
        ).prefetch_related(
            Prefetch(
                'children',
                queryset=Category.objects.filter(is_active=True).annotate(
                    article_count=Count('articles', filter=Q(articles__status='published'))
                )
            )
        )
        
        # Popular tags
        context['popular_tags'] = self._get_popular_tags()
        
        # Preserve query parameters
        params = self.request.GET.copy()
        if 'page' in params:
            params.pop('page')
        context['query_params'] = params.urlencode()
        
        # Current filters
        context['current_filters'] = {
            'q': self.request.GET.get('q', ''),
            'category': self.request.GET.get('category', ''),
            'tag': self.request.GET.get('tag', ''),
            'difficulty': self.request.GET.get('difficulty', ''),
            'status': self.request.GET.get('status', 'published'),
            'sort': self.request.GET.get('sort', '-published_at'),
        }
        
        return context
    
    def _get_popular_tags(self, limit=20):
        """Get most used tags with counts"""
        tag_counts = {}
        articles = Article.objects.filter(
            status='published'
        ).values_list('tags', flat=True)
        
        for tags_str in articles:
            if tags_str:
                for tag in tags_str.split(','):
                    tag = tag.strip().lower()
                    if tag:
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        return sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:limit]


class ArticleDetailView(LoginRequiredMixin, DetailView):
    """Display article with enhanced features"""
    model = Article
    template_name = 'kb/article_detail.html'
    context_object_name = 'article'
    
    def get_object(self, queryset=None):
        article = super().get_object(queryset)
        
        # Check permissions for unpublished articles
        if article.status != 'published':
            if not (self.request.user == article.author or self.request.user.is_staff):
                raise Http404("Article not found")
        
        # Increment view count for published articles
        if article.status == 'published':
            article.increment_views()
        
        return article
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        article = self.object
        
        # Render markdown content
        context['content_html'], context['toc'] = render_markdown(article.content)
        
        # Get related data
        context['images'] = article.images.all()
        context['attachments'] = article.attachments.select_related('uploaded_by')
        context['external_links'] = article.external_links.all()
        
        # Similar articles
        context['similar_articles'] = article.get_similar_articles()
        
        # Version history (for authors and staff)
        if self.request.user == article.author or self.request.user.is_staff:
            context['versions'] = article.versions.select_related('edited_by')[:10]
        
        # User feedback
        user_feedback = None
        if self.request.user.is_authenticated:
            try:
                user_feedback = ArticleFeedback.objects.get(
                    article=article,
                    user=self.request.user
                )
            except ArticleFeedback.DoesNotExist:
                pass
        context['user_feedback'] = user_feedback
        
        # Feedback stats
        total_feedback = article.feedback.count()
        if total_feedback > 0:
            helpful_count = article.feedback.filter(is_helpful=True).count()
            context['helpfulness_percentage'] = round((helpful_count / total_feedback) * 100)
        else:
            context['helpfulness_percentage'] = None
        
        # Forms for editing (if authorized)
        context['can_edit'] = (
            self.request.user == article.author or 
            self.request.user.is_staff
        )
        
        if context['can_edit']:
            context['image_form'] = ArticleImageForm()
            context['attachment_form'] = ArticleAttachmentForm()
            context['link_form'] = ArticleLinkForm()
        
        # Breadcrumbs
        breadcrumbs = [
            {'name': 'Knowledge Base', 'url': reverse('kb:home')},
        ]
        if article.category:
            breadcrumbs.append({
                'name': article.category.name,
                'url': reverse('kb:category_articles', kwargs={'slug': article.category.slug})
            })
        breadcrumbs.append({'name': article.title, 'url': None})
        context['breadcrumbs'] = breadcrumbs
        
        return context


class ArticleCreateView(LoginRequiredMixin, CreateView):
    """Create new article"""
    model = Article
    form_class = ArticleForm
    template_name = 'kb/article_form.html'
    
    def form_valid(self, form):
        article = form.save(commit=False)
        article.author = self.request.user
        article.save()
        form.save_m2m()  # Save many-to-many relationships
        
        # Create initial version
        ArticleVersion.objects.create(
            article=article,
            version_number=1,
            title=article.title,
            content=article.content,
            summary=article.summary,
            edited_by=self.request.user,
            change_notes="Initial version"
        )
        
        messages.success(
            self.request, 
            f"Article '{article.title}' created successfully!"
        )
        
        if article.status == 'published':
            return redirect(article.get_absolute_url())
        else:
            return redirect('kb:article_edit', slug=article.slug)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_create'] = True
        context['categories'] = Category.objects.filter(is_active=True)
        return context


class ArticleUpdateView(LoginRequiredMixin, UpdateView):
    """Update existing article"""
    model = Article
    form_class = ArticleForm
    template_name = 'kb/article_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        article = self.get_object()
        # Check permissions
        if not (request.user == article.author or request.user.is_staff):
            messages.error(request, "You don't have permission to edit this article.")
            return redirect(article.get_absolute_url())
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        article = form.save()
        
        # Create version if content changed
        last_version = article.versions.first()
        if not last_version or (
            last_version.content != article.content or 
            last_version.title != article.title
        ):
            new_version_number = (last_version.version_number + 1) if last_version else 1
            ArticleVersion.objects.create(
                article=article,
                version_number=new_version_number,
                title=article.title,
                content=article.content,
                summary=article.summary,
                edited_by=self.request.user,
                change_notes=self.request.POST.get('change_notes', '')
            )
        
        messages.success(
            self.request, 
            f"Article '{article.title}' updated successfully!"
        )
        return redirect(article.get_absolute_url())
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_create'] = False
        context['categories'] = Category.objects.filter(is_active=True)
        context['versions'] = self.object.versions.select_related('edited_by')[:10]
        return context


class ArticleDeleteView(LoginRequiredMixin, DeleteView):
    """Delete article"""
    model = Article
    template_name = 'kb/article_confirm_delete.html'
    success_url = reverse_lazy('kb:article_list')
    
    def dispatch(self, request, *args, **kwargs):
        article = self.get_object()
        # Check permissions
        if not (request.user == article.author or request.user.is_staff):
            messages.error(request, "You don't have permission to delete this article.")
            return redirect(article.get_absolute_url())
        return super().dispatch(request, *args, **kwargs)
    
    def delete(self, request, *args, **kwargs):
        article = self.get_object()
        messages.success(request, f"Article '{article.title}' deleted successfully.")
        return super().delete(request, *args, **kwargs)


class CategoryArticlesView(LoginRequiredMixin, ListView):
    """List articles in a specific category"""
    model = Article
    template_name = 'kb/category_articles.html'
    context_object_name = 'articles'
    paginate_by = 20
    
    def get_queryset(self):
        self.category = get_object_or_404(
            Category, 
            slug=self.kwargs['slug'],
            is_active=True
        )
        
        # Get articles from this category and its descendants
        categories = [self.category] + self.category.get_descendants()
        
        return Article.objects.filter(
            category__in=categories,
            status='published'
        ).select_related('author', 'category').order_by('-published_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] = self.category
        context['subcategories'] = self.category.children.filter(is_active=True)
        context['breadcrumbs'] = [
            {'name': 'Knowledge Base', 'url': reverse('kb:home')},
            {'name': self.category.name, 'url': None}
        ]
        return context


# AJAX/HTMX Views
@login_required
@require_http_methods(["POST"])
def article_feedback(request, slug):
    """Handle article feedback"""
    article = get_object_or_404(Article, slug=slug)
    is_helpful = request.POST.get('helpful') == 'true'
    comment = request.POST.get('comment', '')
    
    # Get or create feedback
    feedback, created = ArticleFeedback.objects.update_or_create(
        article=article,
        user=request.user,
        defaults={
            'is_helpful': is_helpful,
            'comment': comment
        }
    )
    
    # Update article counters
    article.refresh_from_db()
    if created:
        if is_helpful:
            article.helpful_count = F('helpful_count') + 1
        else:
            article.not_helpful_count = F('not_helpful_count') + 1
        article.save(update_fields=['helpful_count', 'not_helpful_count'])
    
    return JsonResponse({
        'success': True,
        'helpful_count': article.helpful_count,
        'not_helpful_count': article.not_helpful_count,
        'message': 'Thank you for your feedback!'
    })


@login_required
@require_http_methods(["POST"])
def upload_image(request, slug):
    """Upload image for article"""
    article = get_object_or_404(Article, slug=slug)
    
    # Check permissions
    if not (request.user == article.author or request.user.is_staff):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    form = ArticleImageForm(request.POST, request.FILES)
    if form.is_valid():
        image = form.save(commit=False)
        image.article = article
        image.uploaded_by = request.user
        image.save()
        
        return JsonResponse({
            'success': True,
            'id': image.id,
            'url': image.image.url,
            'caption': image.caption,
            'alt_text': image.alt_text
        })
    
    return JsonResponse({
        'success': False,
        'errors': form.errors
    }, status=400)


@login_required
@require_http_methods(["POST"])
def upload_attachment(request, slug):
    """Upload attachment for article"""
    article = get_object_or_404(Article, slug=slug)
    
    # Check permissions
    if not (request.user == article.author or request.user.is_staff):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    form = ArticleAttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        attachment = form.save(commit=False)
        attachment.article = article
        attachment.uploaded_by = request.user
        attachment.save()
        
        return JsonResponse({
            'success': True,
            'id': attachment.id,
            'title': attachment.title,
            'size': attachment.file_size_display,
            'url': attachment.file.url
        })
    
    return JsonResponse({
        'success': False,
        'errors': form.errors
    }, status=400)


@login_required
@require_http_methods(["GET"])
def search_articles(request):
    """AJAX search endpoint"""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})
    
    articles = Article.objects.filter(
        status='published'
    ).filter(
        Q(title__icontains=q) |
        Q(summary__icontains=q) |
        Q(tags__icontains=q)
    ).values(
        'slug', 'title', 'summary', 'category__name'
    )[:10]
    
    results = [{
        'title': article['title'],
        'summary': article['summary'][:100] + '...' if len(article['summary']) > 100 else article['summary'],
        'category': article['category__name'] or 'Uncategorized',
        'url': reverse('kb:article_detail', kwargs={'slug': article['slug']})
    } for article in articles]
    
    return JsonResponse({'results': results})


@login_required  
def article_preview(request):
    """Preview markdown content"""
    if request.method == 'POST':
        content = request.POST.get('content', '')
        html, _ = render_markdown(content)
        return JsonResponse({'html': html})
    return JsonResponse({'error': 'Invalid request'}, status=400)