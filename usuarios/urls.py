from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "usuarios"

# Se mantienen las mismas rutas de la version Java: /, /login, /registro
urlpatterns = [
    path("", views.InicioView.as_view(), name="inicio"),
    path("login", views.IniciarSesionView.as_view(), name="login"),
    path("logout", LogoutView.as_view(), name="logout"),  # solo acepta POST
    path("registro", views.registro, name="registro"),
    path("panel", views.panel, name="panel"),
    # Contraseña y cuenta
    path("recuperar-password", views.recuperar_password, name="recuperar_password"),
    path("restablecer-password", views.restablecer_password, name="restablecer_password"),
    path("cambiar-password", views.cambiar_password, name="cambiar_password"),
    path("perfil", views.perfil, name="perfil"),
    path("perfil/editar", views.editar_perfil, name="editar_perfil"),
    path("cobertura", views.cobertura, name="cobertura"),
    path("cuenta/desactivar", views.desactivar_cuenta, name="desactivar_cuenta"),
]
