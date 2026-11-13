"""Patrón Strategy para comparar el rostro del documento con la selfie.

La versión Java tenía dos estrategias conectadas con Spring:
  - VerificacionFacePlusPlus: llama a la API de Face++ y devuelve la similitud.
  - VerificacionManual: devuelve -1 y deja el intento para revisión humana.

Aquí se conserva la misma idea. La estrategia se elige sola:
  - Si settings.FACEPP_API_KEY y FACEPP_API_SECRET están definidos, se usa Face++.
  - Si no, se usa la manual. Así el proyecto funciona sin pagar APIs externas y
    la verificación automática queda como una mejora opcional.
"""
import json
import mimetypes
import os
import urllib.request
import uuid
from abc import ABC, abstractmethod

from django.conf import settings


class EstrategiaVerificacion(ABC):
    """Interfaz común: recibe dos rutas de imagen y devuelve un porcentaje."""

    automatica = False

    @abstractmethod
    def verificar(self, ruta_documento, ruta_selfie):
        """Similitud de 0 a 100, o -1 si no se pudo calcular."""


class VerificacionManual(EstrategiaVerificacion):
    """Estrategia por defecto: no compara rostros; lo revisa un administrador."""

    automatica = False

    def verificar(self, ruta_documento, ruta_selfie):
        return -1.0


class VerificacionFacePlusPlus(EstrategiaVerificacion):
    """Estrategia real: envía las dos imágenes a la API de Face++."""

    automatica = True

    def __init__(self, api_key, api_secret, url=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.url = url or "https://api-us.faceplusplus.com/facepp/v3/compare"

    def verificar(self, ruta_documento, ruta_selfie):
        try:
            respuesta = self._comparar(ruta_documento, ruta_selfie)
        except (OSError, ValueError, urllib.request.URLError):
            # Si el servicio no responde, el intento no se rechaza: se revisa a mano.
            return -1.0

        confianza = respuesta.get("confidence")
        if isinstance(confianza, (int, float)):
            return float(confianza)
        return -1.0

    def _comparar(self, ruta_documento, ruta_selfie):
        campos = {"api_key": self.api_key, "api_secret": self.api_secret}
        archivos = {"image_file1": ruta_documento, "image_file2": ruta_selfie}
        cuerpo, tipo_contenido = _cuerpo_multipart(campos, archivos)

        solicitud = urllib.request.Request(
            self.url,
            data=cuerpo,
            headers={"Content-Type": tipo_contenido},
            method="POST",
        )
        with urllib.request.urlopen(solicitud, timeout=20) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))


def _cuerpo_multipart(campos, archivos):
    """Arma un formulario multipart sin dependencias externas.

    Se usa la librería estándar para no sumar `requests` solo por esta llamada.
    """
    limite = uuid.uuid4().hex
    partes = []

    for nombre, valor in campos.items():
        partes.append(
            (
                f'--{limite}\r\nContent-Disposition: form-data; name="{nombre}"'
                f"\r\n\r\n{valor}\r\n"
            ).encode("utf-8")
        )

    for nombre, ruta in archivos.items():
        with open(ruta, "rb") as archivo:
            contenido = archivo.read()
        tipo = mimetypes.guess_type(ruta)[0] or "application/octet-stream"
        partes.append(
            (
                f'--{limite}\r\nContent-Disposition: form-data; name="{nombre}"; '
                f'filename="{os.path.basename(ruta)}"\r\nContent-Type: {tipo}\r\n\r\n'
            ).encode("utf-8")
            + contenido
            + b"\r\n"
        )

    partes.append(f"--{limite}--\r\n".encode("utf-8"))
    return b"".join(partes), f"multipart/form-data; boundary={limite}"


def estrategia_actual():
    """Elige la estrategia disponible según la configuración."""
    clave = getattr(settings, "FACEPP_API_KEY", "")
    secreto = getattr(settings, "FACEPP_API_SECRET", "")
    if clave and secreto:
        return VerificacionFacePlusPlus(
            clave, secreto, getattr(settings, "FACEPP_API_URL", None)
        )
    return VerificacionManual()
