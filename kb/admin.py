from django.contrib import admin
from .models import Category, Article, ArticleVersion, ArticleImage, ArticleProjectLink, ArticleAssetLink


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'position', 'article_count']
    list_filter = ['parent']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['position', 'name']
    
    def article_count(self, obj):
        return obj.articles.count()
    article_count.short_description = 'Articles'


class ArticleImageInline(admin.TabularInline):
    model = ArticleImage
    extra = 0
    fields = ['image', 'caption', 'uploaded_by', 'uploaded_at']
    readonly_fields = ['uploaded_by', 'uploaded_at']


class ArticleProjectLinkInline(admin.TabularInline):
    model = ArticleProjectLink
    extra = 0
    fields = ['project', 'task', 'added_by', 'added_at']
    readonly_fields = ['added_by', 'added_at']
    autocomplete_fields = ['project', 'task']


class ArticleAssetLinkInline(admin.TabularInline):
    model = ArticleAssetLink
    extra = 0
    fields = ['asset', 'description', 'added_by', 'added_at']
    readonly_fields = ['added_by', 'added_at']
    autocomplete_fields = ['asset']


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'author', 'status', 'is_pinned', 'views_count', 'published_at']
    list_filter = ['status', 'is_pinned', 'category', 'created_at', 'published_at']
    search_fields = ['title', 'summary', 'content', 'tags']
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    readonly_fields = ['views_count', 'created_at', 'updated_at', 'published_at']
    
    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'summary', 'content')
        }),
        ('Categorization', {
            'fields': ('category', 'tags', 'related_articles')
        }),
        ('Status', {
            'fields': ('status', 'is_pinned', 'author')
        }),
        ('Metadata', {
            'fields': ('views_count', 'created_at', 'updated_at', 'published_at'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [ArticleProjectLinkInline, ArticleAssetLinkInline, ArticleImageInline]
    filter_horizontal = ['related_articles']
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        super().save_model(request, obj, form, change)


@admin.register(ArticleVersion)
class ArticleVersionAdmin(admin.ModelAdmin):
    list_display = ['article', 'version_number', 'edited_by', 'created_at']
    list_filter = ['created_at']
    search_fields = ['article__title', 'change_notes']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    readonly_fields = ['article', 'version_number', 'title', 'content', 'summary', 'edited_by', 'created_at']