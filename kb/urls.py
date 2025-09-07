from django.urls import path
from . import views

app_name = 'kb'

urlpatterns = [
    # Article views
    path('', views.ArticleListView.as_view(), name='article_list'),
    path('article/new/', views.ArticleCreateView.as_view(), name='article_create'),
    path('article/<slug:slug>/', views.ArticleDetailView.as_view(), name='article_detail'),
    path('article/<slug:slug>/edit/', views.ArticleUpdateView.as_view(), name='article_edit'),
    path('article/<slug:slug>/delete/', views.ArticleDeleteView.as_view(), name='article_delete'),
    
    # HTMX endpoints
    path('htmx/project-tasks/', views.get_project_tasks, name='get_project_tasks'),
    path('htmx/article/<slug:slug>/add-project/', views.add_project_link, name='add_project_link'),
    path('htmx/article/<slug:slug>/add-asset/', views.add_asset_link, name='add_asset_link'),
    path('htmx/article/<slug:slug>/upload-image/', views.upload_image, name='upload_image'),
    path('htmx/remove-link/<str:link_type>/<int:link_id>/', views.remove_link, name='remove_link'),
    
    # Category management
    path('categories/', views.CategoryListView.as_view(), name='category_list'),
    path('categories/new/', views.CategoryCreateView.as_view(), name='category_create'),
]