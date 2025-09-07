from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, F
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views.decorators.http import require_http_methods

from accounts.views import RoleRequiredMixin
from accounts.models import UserRole
from projects.models import Project, Task

from .models import Article, Category, ArticleProjectLink, ArticleAssetLink, ArticleImage, ArticleVersion
from .forms import ArticleForm, ProjectTaskLinkForm, AssetLinkForm, ArticleImageForm, CategoryForm

import json
import markdown


PM_OR_DEV = (UserRole.PROJECT_MANAGER, UserRole.DEVELOPER)


class KBRoleGuard(RoleRequiredMixin):
    required_roles = PM_OR_DEV


class ArticleListView(KBRoleGuard, ListView):
    model = Article
    template_name = 'kb/article_list.html'
    context_object_name = 'articles'
    paginate_by = 20
    
    def get_queryset(self):
        qs = Article.objects.select_related('author', 'category').prefetch_related('project_links__project')
        
        # Only show published articles unless viewing own drafts
        if not self.request.GET.get('drafts'):
            qs = qs.filter(status='published')
        elif self.request.GET.get('drafts') == 'mine':
            qs = qs.filter(author=self.request.user, status='draft')
        
        # Search
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(summary__icontains=q) |
                Q(content__icontains=q) |
                Q(tags__icontains=q)
            )
        
        # Category filter
        cat = self.request.GET.get('category')
        if cat:
            qs = qs.filter(category__slug=cat)
        
        # Tag filter
        tag = self.request.GET.get('tag')
        if tag:
            qs = qs.filter(tags__icontains=tag)
        
        # Project filter
        project = self.request.GET.get('project')
        if project and project.isdigit():
            qs = qs.filter(project_links__project_id=project).distinct()
        
        # Sorting
        sort = self.request.GET.get('sort', '-published_at')
        if sort in ['title', '-title', 'views_count', '-views_count', 'published_at', '-published_at']:
            qs = qs.order_by(sort)
        
        return qs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.annotate(article_count=Count('articles'))
        context['popular_tags'] = self._get_popular_tags()
        context['q'] = self.request.GET.get('q', '')
        context['current_category'] = self.request.GET.get('category')
        context['current_tag'] = self.request.GET.get('tag')
        context['sort'] = self.request.GET.get('sort', '-published_at')
        
        # Preserve query params for pagination
        params = self.request.GET.copy()
        params.pop('page', None)
        context['querystring'] = params.urlencode()
        
        return context
    
    def _get_popular_tags(self):
        # Get top 20 most used tags
        tag_counts = {}
        for article in Article.objects.filter(status='published').values('tags'):
            if article['tags']:
                for tag in article['tags'].split(','):
                    tag = tag.strip()
                    if tag:
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]


class ArticleDetailView(KBRoleGuard, DetailView):
    model = Article
    template_name = 'kb/article_detail.html'
    context_object_name = 'article'
    
    def get_object(self):
        obj = super().get_object()
        # Increment view count
        obj.increment_views()
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Convert markdown to HTML
        md = markdown.Markdown(extensions=['extra', 'codehilite', 'toc'])
        context['content_html'] = md.convert(self.object.content)
        
        # Get related data
        context['project_links'] = self.object.project_links.select_related('project', 'task', 'added_by')
        context['asset_links'] = self.object.asset_links.select_related('asset', 'added_by')
        context['images'] = self.object.images.all()
        context['related_articles'] = self.object.related_articles.filter(status='published')[:5]
        
        # Get version history
        context['versions'] = self.object.versions.select_related('edited_by')[:10]
        
        # Forms for adding links (if user is author or PM)
        if self.request.user == self.object.author or hasattr(self.request.user.profile, 'is_project_manager'):
            context['project_form'] = ProjectTaskLinkForm(user=self.request.user)
            context['asset_form'] = AssetLinkForm()
            context['image_form'] = ArticleImageForm()
        
        return context


class ArticleCreateView(KBRoleGuard, CreateView):
    model = Article
    form_class = ArticleForm
    template_name = 'kb/article_form.html'
    
    def form_valid(self, form):
        form.instance.author = self.request.user
        article = form.save()
        
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
        
        messages.success(self.request, f"Article '{article.title}' created successfully.")
        return redirect(article.get_absolute_url())
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_create'] = True
        return context


class ArticleUpdateView(KBRoleGuard, UpdateView):
    model = Article
    form_class = ArticleForm
    template_name = 'kb/article_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        # Only author or PM can edit
        if obj.author != request.user and not getattr(request.user.profile, 'is_project_manager', False):
            messages.error(request, "You don't have permission to edit this article.")
            return redirect(obj.get_absolute_url())
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        article = form.save()
        
        # Create version snapshot if content changed
        last_version = article.versions.first()
        if not last_version or last_version.content != article.content:
            new_version = (last_version.version_number + 1) if last_version else 1
            ArticleVersion.objects.create(
                article=article,
                version_number=new_version,
                title=article.title,
                content=article.content,
                summary=article.summary,
                edited_by=self.request.user,
                change_notes=self.request.POST.get('change_notes', '')
            )
        
        messages.success(self.request, f"Article '{article.title}' updated successfully.")
        return redirect(article.get_absolute_url())
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_create'] = False
        return context


class ArticleDeleteView(KBRoleGuard, DeleteView):
    model = Article
    template_name = 'kb/article_confirm_delete.html'
    success_url = reverse_lazy('kb:article_list')
    
    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        # Only author or PM can delete
        if obj.author != request.user and not getattr(request.user.profile, 'is_project_manager', False):
            messages.error(request, "You don't have permission to delete this article.")
            return redirect(obj.get_absolute_url())
        return super().dispatch(request, *args, **kwargs)
    
    def delete(self, request, *args, **kwargs):
        article = self.get_object()
        messages.success(request, f"Article '{article.title}' deleted successfully.")
        return super().delete(request, *args, **kwargs)


# HTMX endpoints
@login_required
@require_http_methods(["GET"])
def get_project_tasks(request):
    project_id = request.GET.get('project')
    if not project_id:
        return HttpResponse('<option value="">Select a project first</option>')
    
    try:
        tasks = Task.objects.filter(project_id=project_id).order_by('title')
        html = '<option value="">No specific task</option>'
        for task in tasks:
            html += f'<option value="{task.id}">{task.title}</option>'
        return HttpResponse(html)
    except:
        return HttpResponse('<option value="">Error loading tasks</option>')


@login_required
@require_http_methods(["POST"])
def add_project_link(request, slug):
    article = get_object_or_404(Article, slug=slug)
    
    # Check permission
    if article.author != request.user and not getattr(request.user.profile, 'is_project_manager', False):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    form = ProjectTaskLinkForm(request.POST, user=request.user)
    if form.is_valid():
        link = form.save(commit=False)
        link.article = article
        link.added_by = request.user
        link.save()
        
        # Return HTML fragment for HTMX
        return render(request, 'kb/partials/project_link_item.html', {'link': link})
    
    return JsonResponse({'error': 'Invalid form data'}, status=400)


@login_required
@require_http_methods(["POST"])
def add_asset_link(request, slug):
    article = get_object_or_404(Article, slug=slug)
    
    # Check permission
    if article.author != request.user and not getattr(request.user.profile, 'is_project_manager', False):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    form = AssetLinkForm(request.POST)
    if form.is_valid():
        link = form.save(commit=False)
        link.article = article
        link.added_by = request.user
        link.save()
        
        return render(request, 'kb/partials/asset_link_item.html', {'link': link})
    
    return JsonResponse({'error': 'Invalid form data'}, status=400)


@login_required
@require_http_methods(["POST"])
def upload_image(request, slug):
    article = get_object_or_404(Article, slug=slug)
    
    # Check permission
    if article.author != request.user and not getattr(request.user.profile, 'is_project_manager', False):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    form = ArticleImageForm(request.POST, request.FILES)
    if form.is_valid():
        image = form.save(commit=False)
        image.article = article
        image.uploaded_by = request.user
        image.save()
        
        return render(request, 'kb/partials/image_item.html', {'image': image})
    
    return JsonResponse({'error': 'Invalid image data'}, status=400)


@login_required
@require_http_methods(["DELETE"])
def remove_link(request, link_type, link_id):
    if link_type == 'project':
        link = get_object_or_404(ArticleProjectLink, id=link_id)
    elif link_type == 'asset':
        link = get_object_or_404(ArticleAssetLink, id=link_id)
    else:
        return JsonResponse({'error': 'Invalid link type'}, status=400)
    
    article = link.article
    
    # Check permission
    if article.author != request.user and not getattr(request.user.profile, 'is_project_manager', False):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    link.delete()
    return HttpResponse(status=204)


# Category management
class CategoryListView(KBRoleGuard, ListView):
    model = Category
    template_name = 'kb/category_list.html'
    context_object_name = 'categories'
    
    def get_queryset(self):
        return Category.objects.annotate(article_count=Count('articles')).order_by('position', 'name')


class CategoryCreateView(KBRoleGuard, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'kb/category_form.html'
    success_url = reverse_lazy('kb:category_list')
    
    def dispatch(self, request, *args, **kwargs):
        # Only PM can manage categories
        if not getattr(request.user.profile, 'is_project_manager', False):
            messages.error(request, "Only Project Managers can manage categories.")
            return redirect('kb:article_list')
        return super().dispatch(request, *args, **kwargs)