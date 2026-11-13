"""Reglas de los anuncios: publicación del aliado y moderación del administrador."""
from .models import Anuncio


class ErrorAnuncio(Exception):
    """Un error de negocio, con un mensaje listo para mostrarle a la persona."""


def listar_del_aliado(aliado):
    return Anuncio.objects.filter(aliado=aliado).order_by("-fecha_creacion", "-id")


def listar_publicados():
    return Anuncio.objects.filter(estado=Anuncio.Estado.PUBLICADO).order_by("-fecha_creacion")


def listar_por_estado(estado):
    return Anuncio.objects.filter(estado=estado).order_by("-fecha_creacion", "-id")


def buscar(anuncio_id):
    try:
        return Anuncio.objects.get(pk=anuncio_id)
    except Anuncio.DoesNotExist:
        raise ErrorAnuncio("Anuncio no encontrado")


def buscar_del_aliado(anuncio_id, aliado):
    """El anuncio si es del aliado; si no, se comporta como si no existiera."""
    try:
        return Anuncio.objects.get(pk=anuncio_id, aliado=aliado)
    except Anuncio.DoesNotExist:
        raise ErrorAnuncio("Anuncio no encontrado")


def _borrar_imagen(imagen):
    """Elimina el archivo del disco cuando ya no lo usa ningún anuncio."""
    if imagen:
        imagen.delete(save=False)


def crear(aliado, titulo, descripcion, imagen=None):
    return Anuncio.objects.create(
        aliado=aliado,
        titulo=titulo,
        descripcion=descripcion,
        imagen=imagen,
        estado=Anuncio.Estado.PENDIENTE,
    )


def editar(anuncio, titulo, descripcion, imagen=None):
    """Cualquier edición vuelve a revisión, como en la versión Java."""
    imagen_anterior = anuncio.imagen if imagen else None
    anuncio.titulo = titulo
    anuncio.descripcion = descripcion
    if imagen:
        anuncio.imagen = imagen
    anuncio.estado = Anuncio.Estado.PENDIENTE
    anuncio.motivo_rechazo = ""
    anuncio.save()

    if imagen_anterior and imagen_anterior.name != anuncio.imagen.name:
        _borrar_imagen(imagen_anterior)
    return anuncio


def eliminar(anuncio):
    _borrar_imagen(anuncio.imagen)
    anuncio.delete()


def aprobar(anuncio_id):
    anuncio = buscar(anuncio_id)
    anuncio.estado = Anuncio.Estado.PUBLICADO
    anuncio.motivo_rechazo = ""
    anuncio.save(update_fields=["estado", "motivo_rechazo"])
    return anuncio


def rechazar(anuncio_id, motivo):
    anuncio = buscar(anuncio_id)
    anuncio.estado = Anuncio.Estado.RECHAZADO
    anuncio.motivo_rechazo = (motivo or "").strip()[:500] or "Contenido no apropiado"
    anuncio.save(update_fields=["estado", "motivo_rechazo"])
    return anuncio
