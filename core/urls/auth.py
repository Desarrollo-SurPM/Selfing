from django.urls import path
from django.views.generic import RedirectView
from .. import views

urlpatterns = [
    path('', views.home, name='home'),
    path('favicon.ico', RedirectView.as_view(url='/static/images/favicon.png', permanent=True)),
]
