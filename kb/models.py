from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class Category(models.Model):
    """Category for organizing articles"""
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True, db_index=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        'self', 
        null=True, 
        blank=True, 
        on_delete=models.CASCADE, 
        related_name='children'
    )
    icon = models.CharField(
        max_length=50, 
        blank=True, 
        help_text="Optional icon class (e.g., 'book', 'code', 'gear')"
    )
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['position', 'name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['parent', 'position']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            # Ensure unique slug
            if Category.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{self.slug}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        super().save(*args, **kwargs)
    
    def get_absolute_url(self):
        return reverse('kb:category_articles', kwargs={'slug': self.slug})
    
    @property
    def full_path(self):
        """Get the full category path for breadcrumbs"""
        if self.parent:
            return f"{self.parent.full_path} > {self.name}"
        return self.name
    
    @property
    def article_count(self):
        """Get count of published articles in this category"""
        return self.articles.filter(status='published').count()
    
    def get_descendants(self):
        """Get all descendant categories"""
        descendants = []
        children = self.children.filter(is_active=True)
        for child in children:
            descendants.append(child)
            descendants.extend(child.get_descendants())
        return descendants


class Article(models.Model):
    """Main article model for knowledge base entries"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('review', 'Under Review'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    DIFFICULTY_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]
    
    # Core fields
    title = models.CharField(max_length=200, db_index=True)
    slug = models.SlugField(unique=True, blank=True, db_index=True)
    summary = models.TextField(
        max_length=500, 
        help_text="Brief summary for search results and previews"
    )
    content = models.TextField(help_text="Markdown supported")
    
    # Categorization
    category = models.ForeignKey(
        Category, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='articles'
    )
    tags = models.CharField(
        max_length=500, 
        blank=True, 
        help_text="Comma-separated tags",
        db_index=True
    )
    difficulty = models.CharField(
        max_length=20, 
        choices=DIFFICULTY_CHOICES, 
        default='beginner'
    )
    
    # Status and metadata
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='draft', 
        db_index=True
    )
    is_featured = models.BooleanField(default=False, db_index=True)
    is_pinned = models.BooleanField(default=False, db_index=True)
    
    # Authorship and timestamps
    author = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='kb_articles'
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    
    # Engagement metrics
    views_count = models.PositiveIntegerField(default=0, db_index=True)
    helpful_count = models.PositiveIntegerField(default=0)
    not_helpful_count = models.PositiveIntegerField(default=0)
    
    # Reading time estimation (in minutes)
    estimated_reading_time = models.PositiveIntegerField(default=5)
    
    # Related content
    related_articles = models.ManyToManyField(
        'self', 
        blank=True, 
        symmetrical=True
    )
    
    # SEO fields
    meta_description = models.TextField(
        max_length=160, 
        blank=True, 
        help_text="SEO meta description"
    )
    
    class Meta:
        ordering = ['-is_pinned', '-is_featured', '-published_at', '-created_at']
        indexes = [
            models.Index(fields=['status', '-published_at']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['author', 'status']),
            models.Index(fields=['-views_count']),
            models.Index(fields=['is_featured', 'status']),
            models.Index(fields=['is_pinned', 'status']),
        ]
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        # Generate unique slug
        if not self.slug:
            base_slug = slugify(self.title)[:50]
            slug = base_slug
            n = 1
            while Article.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.slug = slug
        
        # Set published_at when first published
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()
        elif self.status != 'published':
            self.published_at = None
        
        # Calculate estimated reading time (rough estimate: 200 words per minute)
        word_count = len(self.content.split())
        self.estimated_reading_time = max(1, word_count // 200)
        
        # Generate meta description if not provided
        if not self.meta_description and self.summary:
            self.meta_description = self.summary[:160]
        
        super().save(*args, **kwargs)
    
    def get_absolute_url(self):
        return reverse('kb:article_detail', kwargs={'slug': self.slug})
    
    @property
    def tag_list(self):
        """Return tags as a list"""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',') if t.strip()]
    
    def increment_views(self):
        """Increment view count"""
        self.views_count = models.F('views_count') + 1
        self.save(update_fields=['views_count'])
    
    def mark_helpful(self, is_helpful=True):
        """Mark article as helpful or not helpful"""
        if is_helpful:
            self.helpful_count = models.F('helpful_count') + 1
            self.save(update_fields=['helpful_count'])
        else:
            self.not_helpful_count = models.F('not_helpful_count') + 1
            self.save(update_fields=['not_helpful_count'])
    
    @property
    def helpfulness_percentage(self):
        """Calculate helpfulness percentage"""
        total = self.helpful_count + self.not_helpful_count
        if total == 0:
            return None
        return round((self.helpful_count / total) * 100)
    
    def get_similar_articles(self, limit=5):
        """Get similar articles based on category and tags"""
        similar = Article.objects.filter(
            status='published'
        ).exclude(pk=self.pk)
        
        # Prioritize same category
        if self.category:
            similar = similar.filter(category=self.category)
        
        # If we have tags, look for articles with similar tags
        if self.tags:
            tag_queries = models.Q()
            for tag in self.tag_list:
                tag_queries |= models.Q(tags__icontains=tag)
            similar = similar.filter(tag_queries)
        
        return similar.distinct()[:limit]


class ArticleVersion(models.Model):
    """Version history for articles"""
    article = models.ForeignKey(
        Article, 
        on_delete=models.CASCADE, 
        related_name='versions'
    )
    version_number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    content = models.TextField()
    summary = models.TextField(max_length=500)
    change_notes = models.TextField(blank=True)
    edited_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-version_number']
        unique_together = [['article', 'version_number']]
        indexes = [
            models.Index(fields=['article', '-version_number']),
        ]
    
    def __str__(self):
        return f"{self.article.title} v{self.version_number}"
    
    def restore(self):
        """Restore this version as the current article content"""
        self.article.title = self.title
        self.article.content = self.content
        self.article.summary = self.summary
        self.article.save()
        
        # Create a new version for the restoration
        ArticleVersion.objects.create(
            article=self.article,
            version_number=self.article.versions.count() + 1,
            title=self.title,
            content=self.content,
            summary=self.summary,
            edited_by=self.edited_by,
            change_notes=f"Restored from version {self.version_number}"
        )


class ArticleImage(models.Model):
    """Images attached to articles"""
    article = models.ForeignKey(
        Article, 
        on_delete=models.CASCADE, 
        related_name='images'
    )
    image = models.ImageField(upload_to='kb/images/%Y/%m/')
    caption = models.CharField(max_length=200, blank=True)
    alt_text = models.CharField(
        max_length=200, 
        blank=True, 
        help_text="Alternative text for accessibility"
    )
    uploaded_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    position = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['position', '-uploaded_at']
    
    def __str__(self):
        return f"Image for {self.article.title}"
    
    def save(self, *args, **kwargs):
        # Generate alt text from caption if not provided
        if not self.alt_text and self.caption:
            self.alt_text = self.caption
        super().save(*args, **kwargs)


class ArticleAttachment(models.Model):
    """File attachments for articles"""
    article = models.ForeignKey(
        Article, 
        on_delete=models.CASCADE, 
        related_name='attachments'
    )
    file = models.FileField(upload_to='kb/attachments/%Y/%m/')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file_size = models.PositiveIntegerField(default=0)  # in bytes
    uploaded_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    download_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"Attachment: {self.title}"
    
    def save(self, *args, **kwargs):
        # Calculate file size
        if self.file:
            self.file_size = self.file.size
        super().save(*args, **kwargs)
    
    @property
    def file_size_display(self):
        """Return human-readable file size"""
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"


class ArticleFeedback(models.Model):
    """User feedback on articles"""
    article = models.ForeignKey(
        Article, 
        on_delete=models.CASCADE, 
        related_name='feedback'
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        blank=True
    )
    is_helpful = models.BooleanField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    session_key = models.CharField(
        max_length=40, 
        blank=True, 
        help_text="For anonymous feedback tracking"
    )
    
    class Meta:
        ordering = ['-created_at']
        # Prevent duplicate feedback from same user or session
        unique_together = [
            ['article', 'user'],
            ['article', 'session_key'],
        ]
    
    def __str__(self):
        return f"Feedback for {self.article.title}"


# Optional: Link to external resources
class ArticleLink(models.Model):
    """External links related to articles"""
    article = models.ForeignKey(
        Article, 
        on_delete=models.CASCADE, 
        related_name='external_links'
    )
    title = models.CharField(max_length=200)
    url = models.URLField()
    description = models.TextField(blank=True)
    link_type = models.CharField(
        max_length=20,
        choices=[
            ('documentation', 'Documentation'),
            ('tutorial', 'Tutorial'),
            ('reference', 'Reference'),
            ('tool', 'Tool'),
            ('other', 'Other'),
        ],
        default='other'
    )
    added_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True
    )
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['link_type', 'title']
    
    def __str__(self):
        return f"{self.title} ({self.article.title})"