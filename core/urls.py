from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('ap_app.urls')),
    
    # We will let React router handle other routes
    re_path(r'^.*', TemplateView.as_view(template_name='index.html')),
]

if settings.DEBUG:
    # Ensure Django serves up the root build folder (e.g. for CSS, media files if needed)
    urlpatterns += static('/static/', document_root=settings.STATICFILES_DIRS[0])
