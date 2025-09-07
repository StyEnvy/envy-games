from django import forms
from django.db.models import Q
from .models import Article, Category, ArticleProjectLink, ArticleAssetLink, ArticleImage


class ArticleForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'select select-bordered w-full'})
    )
    
    class Meta:
        model = Article
        fields = ['title', 'summary', 'content', 'category', 'tags', 'status', 'is_pinned']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Article title'
            }),
            'summary': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 2,
                'placeholder': 'Brief summary for search results'
            }),
            'content': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full font-mono text-sm',
                'rows': 20,
                'placeholder': '# Markdown supported\n\nWrite your article content here...'
            }),
            'tags': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'setup, configuration, troubleshooting'
            }),
            'status': forms.Select(attrs={'class': 'select select-bordered w-full'}),
            'is_pinned': forms.CheckboxInput(attrs={'class': 'checkbox checkbox-primary'}),
        }
    
    def clean_tags(self):
        tags = self.cleaned_data.get('tags', '')
        # Normalize tags: lowercase, trim, dedupe
        tag_list = []
        seen = set()
        for tag in tags.split(','):
            tag = tag.strip().lower()
            if tag and tag not in seen:
                seen.add(tag)
                tag_list.append(tag)
        return ', '.join(tag_list)


class ProjectTaskLinkForm(forms.ModelForm):
    project = forms.ModelChoiceField(
        queryset=None,
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full',
            'hx-get': '/app/kb/htmx/project-tasks/',
            'hx-target': '#task-select',
            'hx-trigger': 'change'
        })
    )
    task = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full',
            'id': 'task-select'
        })
    )
    
    class Meta:
        model = ArticleProjectLink
        fields = ['project', 'task']
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Import here to avoid circular dependency
        from projects.models import Project, Task
        from accounts.models import UserRole
        
        # Set project queryset based on user role
        if user and hasattr(user, 'profile'):
            projects = Project.objects.filter(status__in=['planning', 'active'])
            if user.profile.role == UserRole.DEVELOPER:
                projects = projects.filter(
                    Q(memberships__user=user) | Q(created_by=user)
                ).distinct()
            self.fields['project'].queryset = projects.order_by('title')
        else:
            self.fields['project'].queryset = Project.objects.none()
        
        self.fields['task'].queryset = Task.objects.none()
        
        if self.data:
            try:
                project_id = int(self.data.get('project'))
                self.fields['task'].queryset = Task.objects.filter(project_id=project_id).order_by('title')
            except (ValueError, TypeError):
                pass


class AssetLinkForm(forms.ModelForm):
    class Meta:
        model = ArticleAssetLink
        fields = ['asset', 'description']
        widgets = {
            'asset': forms.Select(attrs={'class': 'select select-bordered w-full'}),
            'description': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Optional description'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from assetcatalog.models import Asset
        self.fields['asset'].queryset = Asset.objects.select_related('current_version').order_by('title')


class ArticleImageForm(forms.ModelForm):
    class Meta:
        model = ArticleImage
        fields = ['image', 'caption']
        widgets = {
            'image': forms.FileInput(attrs={
                'class': 'file-input file-input-bordered w-full',
                'accept': 'image/*'
            }),
            'caption': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Optional caption'
            }),
        }
    
    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            if image.size > 5 * 1024 * 1024:  # 5MB limit
                raise forms.ValidationError("Image file too large (max 5MB)")
            if not image.content_type.startswith('image/'):
                raise forms.ValidationError("File must be an image")
        return image


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'parent', 'position']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3
            }),
            'parent': forms.Select(attrs={'class': 'select select-bordered w-full'}),
            'position': forms.NumberInput(attrs={'class': 'input input-bordered w-full'}),
        }