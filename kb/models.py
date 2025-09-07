from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='children')
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['position', 'name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['parent', 'position']),
        ]
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    @property
    def full_path(self):
        if self.parent:
            return f"{self.parent.full_path} > {self.name}"
        return self.name


class Article(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True, db_index=True)
    summary = models.TextField(max_length=500, help_text="Brief summary for search results")
    content = models.TextField(help_text="Markdown supported")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='articles')
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='kb_articles')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    views_count = models.PositiveIntegerField(default=0)
    is_pinned = models.BooleanField(default=False)
    
    # Related content
    related_articles = models.ManyToManyField('self', blank=True, symmetrical=True)
    
    class Meta:
        ordering = ['-is_pinned', '-published_at', '-created_at']
        indexes = [
            models.Index(fields=['status', 'published_at']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['author', 'status']),
            models.Index(fields=['-views_count']),
        ]
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)[:50]
            slug = base_slug
            n = 1
            while Article.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.slug = slug
        
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    def get_absolute_url(self):
        return reverse('kb:article_detail', kwargs={'slug': self.slug})
    
    @property
    def tag_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()]
    
    def increment_views(self):
        self.views_count += 1
        self.save(update_fields=['views_count'])


class ArticleVersion(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    content = models.TextField()
    summary = models.TextField(max_length=500)
    change_notes = models.TextField(blank=True)
    edited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-version_number']
        unique_together = [['article', 'version_number']]
        indexes = [
            models.Index(fields=['article', '-version_number']),
        ]
    
    def __str__(self):
        return f"{self.article.title} v{self.version_number}"


class ArticleImage(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='kb/images/%Y/%m/')
    caption = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"Image for {self.article.title}"


class ArticleProjectLink(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='project_links')
    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='kb_articles')
    task = models.ForeignKey('projects.Task', on_delete=models.CASCADE, null=True, blank=True, related_name='kb_articles')
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-added_at']
        unique_together = [['article', 'project', 'task']]
        indexes = [
            models.Index(fields=['article', 'project']),
            models.Index(fields=['project', 'task']),
        ]
    
    def __str__(self):
        if self.task:
            return f"{self.article.title} -> {self.project.title} -> {self.task.title}"
        return f"{self.article.title} -> {self.project.title}"


class ArticleAssetLink(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='asset_links')
    asset = models.ForeignKey('assetcatalog.Asset', on_delete=models.CASCADE, related_name='kb_articles')
    description = models.CharField(max_length=200, blank=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-added_at']
        unique_together = [['article', 'asset']]
    
    def __str__(self):
        return f"{self.article.title} -> {self.asset.title}"