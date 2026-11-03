"""Validación de archivos subidos (equivale a ValidacionArchivosService.java)."""
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

EXTENSIONES_PERMITIDAS = ["jpg", "jpeg", "png", "webp", "gif", "pdf", "heic", "heif"]
MIMES_PERMITIDOS = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "application/pdf", "image/heic", "image/heif",
}

# Validador de extensión para los campos de archivo de los modelos
validar_extension = FileExtensionValidator(allowed_extensions=EXTENSIONES_PERMITIDAS)


def validar_mime(archivo):
    """Comprueba también el tipo MIME enviado por el navegador (solo en subidas nuevas)."""
    mime = (getattr(archivo, "content_type", "") or "").lower()
    if mime and mime not in MIMES_PERMITIDOS:
        raise ValidationError("El tipo de archivo no coincide con un formato permitido (imagen o PDF).")
    return archivo
