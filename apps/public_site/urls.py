"""Định tuyến M6 — Trang công khai và quản lý tin tức/sách mới."""

from django.urls import path

from apps.public_site import views

app_name = "public_site"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("gioi-thieu/", views.AboutView.as_view(), name="about"),
    path("quy-trinh/", views.ProcessView.as_view(), name="process"),
    path("bieu-mau/", views.FormsView.as_view(), name="forms"),
    path("bieu-mau/<int:pk>/tai/", views.FormDownloadView.as_view(), name="form_download"),
    # Quản lý (EDITOR) — đặt trước /tin-tuc/<slug>/ để không bị bắt nhầm
    path("tin-tuc/quan-ly/", views.NewsManageListView.as_view(), name="news_manage"),
    path("tin-tuc/quan-ly/them/", views.NewsCreateView.as_view(), name="news_create"),
    path("tin-tuc/quan-ly/<int:pk>/sua/", views.NewsUpdateView.as_view(), name="news_update"),
    path("tin-tuc/quan-ly/<int:pk>/dang/", views.NewsPublishView.as_view(), name="news_publish"),
    path("sach-moi/quan-ly/", views.BookManageListView.as_view(), name="book_manage"),
    path("sach-moi/quan-ly/them/", views.BookCreateView.as_view(), name="book_create"),
    path("sach-moi/quan-ly/<int:pk>/sua/", views.BookUpdateView.as_view(), name="book_update"),
    path("sach-moi/quan-ly/<int:pk>/dang/", views.BookPublishView.as_view(), name="book_publish"),
    # Công khai
    path("tin-tuc/", views.NewsListView.as_view(), name="news_list"),
    path("tin-tuc/<slug:slug>/", views.NewsDetailView.as_view(), name="news_detail"),
    path("sach-moi/", views.BooksView.as_view(), name="books"),
    path("lien-he/", views.ContactView.as_view(), name="contact"),
    path("anh/<str:kind>/<int:pk>/", views.CoverImageView.as_view(), name="image"),
]
