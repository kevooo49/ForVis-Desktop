"""formulavis URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
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

from django.conf.urls import url, include, static
from django.contrib import admin
from rest_framework_jwt.views import refresh_jwt_token, verify_jwt_token
from django.contrib.auth.views import logout
from formulavis import settings
from profiles.urls import urlpatterns as profile
from profiles.views import ObtainLoginTokenView

urlpatterns = [
    url(r'^api/admin/', admin.site.urls),

    url(r'^api/profile/', include(profile)),

    url(r'^api/auth/api-token-auth/', ObtainLoginTokenView.as_view()),
    url(r'^api/auth/api-token-refresh/', refresh_jwt_token),
    url(r'^api/auth/api-token-verify/', verify_jwt_token),

    url(r'^api/logout', logout, {'next_page': settings.LOGOUT_REDIRECT_URL}),
] + static.static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

