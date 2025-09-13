from django.urls import path
from . import views

app_name = 'kb'

urlpatterns = [
    # Main views
    path('', views.KBHomeView.as_view(), name='home'),
    path('articles/', views.ArticleListView.as_view(), name='article_list'),
    
    # Article CRUD
    path('article/new/', views.ArticleCreateView.as_view(), name='article_create'),
    path('article/<slug:slug>/', views.ArticleDetailView.as_view(), name='article_detail'),
    path('article/<slug:slug>/edit/', views.ArticleUpdateView.as_view(), name='article_edit'),
    path('article/<slug:slug>/delete/', views.ArticleDeleteView.as_view(), name='article_delete'),
    
    # Category views
    path('category/<slug:slug>/', views.CategoryArticlesView.as_view(), name='category_articles'),
    
    # AJAX/HTMX endpoints
    path('ajax/search/', views.search_articles, name='search_articles'),
    path('ajax/preview/', views.article_preview, name='article_preview'),
    path('ajax/article/<slug:slug>/feedback/', views.article_feedback, name='article_feedback'),
    path('ajax/article/<slug:slug>/upload-image/', views.upload_image, name='upload_image'),
    path('ajax/article/<slug:slug>/upload-attachment/', views.upload_attachment, name='upload_attachment'),
]