from django import forms
from django.core.exceptions import ValidationError
from .models import (
    Article, Category, ArticleImage, ArticleAttachment, 
    ArticleLink, ArticleFeedback
)
from .utils import normalize_tags


class ArticleForm(forms.ModelForm):
    """Form for creating and editing articles"""
    
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full',
            'data-placeholder': 'Select a category'
        })
    )
    
    tags = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full',
            'placeholder': 'Enter tags separated by commas (e.g., python, django, tutorial)',
            'data-role': 'tagsinput'
        })
    )
    
    related_articles = forms.ModelMultipleChoiceField(
        queryset=Article.objects.filter(status='published'),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'select select-bordered w-full',
            'size': '5',
            'data-placeholder': 'Select related articles'
        })
    )
    
    class Meta:
        model = Article
        fields = [
            'title', 'slug', 'summary', 'content', 'category', 
            'tags', 'difficulty', 'status', 'is_featured', 
            'is_pinned', 'related_articles', 'meta_description'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Enter article title',
                'maxlength': '200'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Leave blank to auto-generate from title'
            }),
            'summary': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Brief summary for search results and previews (max 500 characters)',
                'maxlength': '500'
            }),
            'content': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full font-mono text-sm',
                'rows': 20,
                'placeholder': '# Article Title\n\nWrite your content here...\n\n## Section 1\n\nMarkdown is supported!',
                'data-provide': 'markdown',
                'data-autofocus': 'true'
            }),
            'difficulty': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'status': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'is_featured': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'is_pinned': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'meta_description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 2,
                'placeholder': 'SEO meta description (max 160 characters)',
                'maxlength': '160'
            })
        }
        help_texts = {
            'slug': 'URL-friendly version of the title. Leave blank to auto-generate.',
            'is_featured': 'Featured articles appear on the KB home page',
            'is_pinned': 'Pinned articles appear at the top of lists',
            'meta_description': 'Used for SEO. If blank, summary will be used.'
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make slug field not required
        self.fields['slug'].required = False
        
        # Update queryset for related articles to exclude current article
        if self.instance.pk:
            self.fields['related_articles'].queryset = Article.objects.filter(
                status='published'
            ).exclude(pk=self.instance.pk)
        
        # Add CSS classes for better styling
        for field_name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                if isinstance(field.widget, forms.CheckboxInput):
                    field.widget.attrs['class'] = 'checkbox checkbox-primary'
                elif isinstance(field.widget, forms.Select):
                    field.widget.attrs['class'] = 'select select-bordered w-full'
                else:
                    field.widget.attrs['class'] = 'input input-bordered w-full'
    
    def clean_tags(self):
        """Normalize and validate tags"""
        tags = self.cleaned_data.get('tags', '')
        return normalize_tags(tags)
    
    def clean_slug(self):
        """Validate slug uniqueness"""
        slug = self.cleaned_data.get('slug', '')
        if slug:
            # Check if slug is unique (excluding current instance)
            qs = Article.objects.filter(slug=slug)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError('An article with this slug already exists.')
        return slug
    
    def clean(self):
        """Additional validation"""
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        content = cleaned_data.get('content', '')
        
        # Require content for published articles
        if status == 'published' and len(content.strip()) < 100:
            raise ValidationError({
                'content': 'Published articles must have at least 100 characters of content.'
            })
        
        return cleaned_data


class CategoryForm(forms.ModelForm):
    """Form for creating and editing categories"""
    
    parent = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full'
        })
    )
    
    class Meta:
        model = Category
        fields = ['name', 'slug', 'description', 'parent', 'icon', 'position', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Category name'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Leave blank to auto-generate'
            }),
            'description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Brief description of this category'
            }),
            'icon': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Optional icon class (e.g., book, code)'
            }),
            'position': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'min': '0'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False
        
        # Prevent category from being its own parent
        if self.instance.pk:
            self.fields['parent'].queryset = Category.objects.filter(
                is_active=True
            ).exclude(pk=self.instance.pk)
    
    def clean_parent(self):
        """Prevent circular references"""
        parent = self.cleaned_data.get('parent')
        if parent and self.instance.pk:
            # Check if setting this parent would create a circular reference
            current = parent
            while current:
                if current.pk == self.instance.pk:
                    raise ValidationError('Cannot set a descendant as parent.')
                current = current.parent
        return parent


class ArticleImageForm(forms.ModelForm):
    """Form for uploading article images"""
    
    class Meta:
        model = ArticleImage
        fields = ['image', 'caption', 'alt_text', 'position']
        widgets = {
            'image': forms.FileInput(attrs={
                'class': 'file-input file-input-bordered w-full',
                'accept': 'image/*'
            }),
            'caption': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Image caption (optional)'
            }),
            'alt_text': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Alternative text for accessibility'
            }),
            'position': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'min': '0'
            })
        }
    
    def clean_image(self):
        """Validate image file"""
        image = self.cleaned_data.get('image')
        if image:
            # Check file size (max 10MB)
            if image.size > 10 * 1024 * 1024:
                raise ValidationError('Image file too large (max 10MB)')
            
            # Check file type
            allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
            if hasattr(image, 'content_type') and image.content_type not in allowed_types:
                raise ValidationError('Invalid image format. Allowed: JPEG, PNG, GIF, WebP')
        
        return image


class ArticleAttachmentForm(forms.ModelForm):
    """Form for uploading article attachments"""
    
    class Meta:
        model = ArticleAttachment
        fields = ['file', 'title', 'description']
        widgets = {
            'file': forms.FileInput(attrs={
                'class': 'file-input file-input-bordered w-full'
            }),
            'title': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Attachment title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 2,
                'placeholder': 'Brief description (optional)'
            })
        }
    
    def clean_file(self):
        """Validate attachment file"""
        file = self.cleaned_data.get('file')
        if file:
            # Check file size (max 50MB)
            if file.size > 50 * 1024 * 1024:
                raise ValidationError('File too large (max 50MB)')
            
            # Check file extension
            import os
            ext = os.path.splitext(file.name)[1].lower()
            allowed_extensions = [
                '.pdf', '.doc', '.docx', '.xls', '.xlsx', 
                '.ppt', '.pptx', '.txt', '.csv', '.zip', 
                '.tar', '.gz', '.json', '.xml', '.yaml'
            ]
            if ext not in allowed_extensions:
                raise ValidationError(
                    f'File type not allowed. Allowed types: {", ".join(allowed_extensions)}'
                )
        
        return file


class ArticleLinkForm(forms.ModelForm):
    """Form for adding external links"""
    
    class Meta:
        model = ArticleLink
        fields = ['title', 'url', 'description', 'link_type']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Link title'
            }),
            'url': forms.URLInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'https://example.com'
            }),
            'description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 2,
                'placeholder': 'Brief description (optional)'
            }),
            'link_type': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            })
        }
    
    def clean_url(self):
        """Validate URL"""
        url = self.cleaned_data.get('url')
        if url:
            # Basic URL validation
            if not url.startswith(('http://', 'https://')):
                raise ValidationError('URL must start with http:// or https://')
        return url


class ArticleFeedbackForm(forms.ModelForm):
    """Form for article feedback"""
    
    class Meta:
        model = ArticleFeedback
        fields = ['is_helpful', 'comment']
        widgets = {
            'is_helpful': forms.RadioSelect(
                choices=[(True, 'Yes'), (False, 'No')],
                attrs={'class': 'radio radio-primary'}
            ),
            'comment': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Additional feedback (optional)'
            })
        }


class ArticleSearchForm(forms.Form):
    """Advanced search form"""
    
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full',
            'placeholder': 'Search articles...'
        })
    )
    
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        empty_label='All Categories',
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full'
        })
    )
    
    tags = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full',
            'placeholder': 'Filter by tags'
        })
    )
    
    difficulty = forms.ChoiceField(
        choices=[('', 'All Levels')] + Article.DIFFICULTY_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full'
        })
    )
    
    status = forms.ChoiceField(
        choices=[
            ('published', 'Published'),
            ('my_drafts', 'My Drafts'),
            ('all', 'All Articles')
        ],
        initial='published',
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full'
        })
    )
    
    sort = forms.ChoiceField(
        choices=[
            ('-published_at', 'Newest First'),
            ('published_at', 'Oldest First'),
            ('title', 'Title (A-Z)'),
            ('-title', 'Title (Z-A)'),
            ('-views_count', 'Most Viewed'),
            ('-helpful_count', 'Most Helpful')
        ],
        initial='-published_at',
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full'
        })
    )