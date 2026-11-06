from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.views.generic import TemplateView
from django.urls import include, path

urlpatterns = [
    path('', staff_member_required(TemplateView.as_view(template_name='index.html'), login_url='/admin/login/'), name='dashboard'),
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
    path('api-auth/', include('rest_framework.urls')),
]
