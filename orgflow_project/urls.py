"""
URL configuration for orgflow_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""
from django.contrib import admin
from django.urls import include, path, register_converter

from core.converters import ObjectIdConverter

register_converter(ObjectIdConverter, "oid")

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('accounts/', include('accounts.urls')),
    path('membership/', include('membership.urls')),
    path('committees/', include('committees.urls')),
    path('meetings/', include('meetings.urls')),
]
