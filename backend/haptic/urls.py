from django.urls import path

from . import views

urlpatterns = [
    path("policies/", views.PolicyListView.as_view(), name="policy-list"),
    path("policies/<str:code>/", views.PolicyDetailView.as_view(), name="policy-detail"),
    path("policies/<str:code>/motors/", views.PolicyMotorsUpdateView.as_view(), name="policy-motors-update"),
    path("policies/<str:code>/activate/", views.PolicyActivateView.as_view(), name="policy-activate"),
    path("status/", views.StatusView.as_view(), name="status"),
    path("stop/", views.StopView.as_view(), name="stop"),
]
