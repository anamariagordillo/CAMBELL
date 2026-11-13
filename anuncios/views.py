"""Pantallas de anuncios del aliado comercial."""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from usuarios.models import Rol
from usuarios.permisos import rol_requerido

from . import servicios
from .forms import AnuncioForm
from .servicios import ErrorAnuncio

SOLO_ALIADO = rol_requerido(Rol.ALIADO_COMERCIAL)


@SOLO_ALIADO
def mios(request):
    return render(request, "anuncios/mis_anuncios.html", {
        "anuncios": servicios.listar_del_aliado(request.user),
    })


@SOLO_ALIADO
def nuevo(request):
    if request.method == "POST":
        form = AnuncioForm(request.POST, request.FILES)
        if form.is_valid():
            servicios.crear(request.user, **form.cleaned_data)
            messages.success(
                request,
                "Tu anuncio quedó en revisión. Un administrador lo aprobará pronto.",
            )
            return redirect("anuncios:mios")
    else:
        form = AnuncioForm()

    return render(request, "anuncios/formulario.html", {
        "form": form,
        "es_edicion": False,
    })


@SOLO_ALIADO
def editar(request, anuncio_id):
    try:
        anuncio = servicios.buscar_del_aliado(anuncio_id, request.user)
    except ErrorAnuncio as error:
        messages.error(request, str(error))
        return redirect("anuncios:mios")

    if request.method == "POST":
        form = AnuncioForm(request.POST, request.FILES, instance=anuncio)
        if form.is_valid():
            servicios.editar(
                anuncio,
                form.cleaned_data["titulo"],
                form.cleaned_data["descripcion"],
                form.cleaned_data.get("imagen"),
            )
            messages.success(
                request,
                "Anuncio actualizado. Volverá a revisión antes de publicarse.",
            )
            return redirect("anuncios:mios")
    else:
        form = AnuncioForm(instance=anuncio)

    return render(request, "anuncios/formulario.html", {
        "form": form,
        "anuncio": anuncio,
        "es_edicion": True,
    })


@require_POST
@SOLO_ALIADO
def eliminar(request, anuncio_id):
    try:
        anuncio = servicios.buscar_del_aliado(anuncio_id, request.user)
        servicios.eliminar(anuncio)
        messages.success(request, "Anuncio eliminado.")
    except ErrorAnuncio as error:
        messages.error(request, str(error))
    return redirect("anuncios:mios")
