# en user/urls.py
from django.urls import path
from .views import SupervisorListView

urlpatterns = [
    path('supervisores/', SupervisorListView.as_view(), name='supervisores'),
]
