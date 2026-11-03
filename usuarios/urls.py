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
]
