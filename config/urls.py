from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

# Nombres del panel de gestión de Django (opcional, solo cambia los textos)
admin.site.site_header = "Cambell · Gestión"
admin.site.site_title = "Cambell"
admin.site.index_title = "Panel de gestión"

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("solicitudes/", include("solicitudes.urls")),
    path("", include("usuarios.urls")),
]

if settings.DEBUG:
    # Solo las imágenes de anuncios son públicas. Documentos, selfies y documentos
    # legales NO se sirven por URL (se verán desde una vista protegida, fase 4).
    urlpatterns += [
        re_path(
            r"^uploads/anuncios/(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT / "anuncios"},
        ),
    ]