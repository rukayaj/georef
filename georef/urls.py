"""georef URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.9/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url
from django.contrib import admin
from website import views
from website.views import DeleteGeoreference
from django.conf.urls import include


urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^$', views.index, name='index'),
    url(r'^completed/$', views.completed, name='completed'),
    url(r'^qc/$', views.qc, name='qc'),
    url(r'^add/bulk/', views.add_bulk, name='add_bulk'),
    url(r'^georeference/(?P<pk>[0-9]+)/$', views.GeoReferenceUpdateView.as_view(), name='georeference'),
    url(r'^georeference/(?P<pk>[0-9]+)/auto_geolocate/', views.auto_geolocate, name='auto_geolocate'),

    url(r'^process_bulk', views.process_bulk, name='process_bulk'),
    url(r'^set-geographical-position/(?P<pk>[0-9]+)/', views.set_geographical_position, name='set_geographical_position'),

    url(r'^delete/(?P<pk>[0-9]+)/$', DeleteGeoreference.as_view(), name='delete'),

    # Just for debugging
    url(r'^georeference/(?P<pk>[0-9]+)/clean_locality/', views.clean_locality, name='clean_locality'),
    url(r'^import/shp/(?P<shp_name>\w+)/$', views.import_shp, name='import_shp'),
    url(r'^import/csv/$', views.import_csv, name='import_csv'),

    # Accounts
    url('^accounts/', include('django.contrib.auth.urls')),
    # url(r'^accounts/', include('accounts.urls', namespace='accounts')),
]
