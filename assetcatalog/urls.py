from django.urls import path
from .views import AssetListView, AssetDetailView, AssetCreateView, UploadVersionView, DownloadVersionView

app_name = "assetcatalog"

urlpatterns = [
    path("", AssetListView.as_view(), name="list"),
    path("create/", AssetCreateView.as_view(), name="create"),
    path("<slug:slug>/", AssetDetailView.as_view(), name="detail"),
    path("<slug:slug>/upload/", UploadVersionView.as_view(), name="upload_version"),
    path("download/<int:version_id>/", DownloadVersionView.as_view(), name="download_version"),
]
