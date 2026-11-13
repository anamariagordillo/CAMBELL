"""Trabajos programados de Cambell.

Equivale a TareasProgramadasService.java. Cada función es una tarea independiente
y devuelve un pequeño resumen (conteos) para poder mostrarlo en la terminal.

Se ejecutan con el comando:

    python manage.py tareas_programadas            # todas
    python manage.py tareas_programadas --tarea reasignar

En producción se pueden llamar desde `cron` o desde el Programador de tareas.
"""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from mensajeria.servicios import crear_notificacion
from pagos import cobros
from pagos import suscripcion as servicio_suscripcion
from seguridad.models import ReporteSeguridad
from solicitudes.models import EstadoSolicitud, Solicitud
from solicitudes.observadores import EventoSolicitud, TipoEvento, notificador
from usuarios.models import Archivo, DocumentoVersion, Rol, Usuario


# ------------------------------------------------------------------ 1. Reasignación
def reasignar_solicitudes_sin_respuesta():
    """Vuelve a avisar de las solicitudes pendientes que nadie ha tomado.

    Se toma como referencia la última reasignación (o la creación si nunca se
    reasignó) y se avisa otra vez a los trabajadores compatibles.
    """
    limite = timezone.now() - timedelta(hours=settings.HORAS_REASIGNACION)
    pendientes = list(
        Solicitud.objects.filter(estado=EstadoSolicitud.PENDIENTE).select_related(
            "cliente", "trabajador"
        )
    )

    reasignadas = 0
    for solicitud in pendientes:
        referencia = solicitud.fecha_ultima_reasignacion or solicitud.fecha_creacion
        if referencia is None or referencia >= limite:
            continue

        solicitud.fecha_ultima_reasignacion = timezone.now()
        solicitud.save(update_fields=["fecha_ultima_reasignacion"])
        notificador.notificar(EventoSolicitud(TipoEvento.REASIGNADA, solicitud))
        reasignadas += 1

    return {"revisadas": len(pendientes), "reasignadas": reasignadas}


# ------------------------------------------------------------------ 2. No atendidas
def cerrar_solicitudes_no_atendidas():
    """Cierra como NO_ATENDIDA las solicitudes pendientes demasiado antiguas."""
    limite = timezone.now() - timedelta(hours=settings.HORAS_SOLICITUD_NO_ATENDIDA)
    antiguas = Solicitud.objects.filter(
        estado=EstadoSolicitud.PENDIENTE, fecha_creacion__lt=limite
    ).select_related("cliente")

    cerradas = 0
    for solicitud in antiguas:
        solicitud.estado = EstadoSolicitud.NO_ATENDIDA
        solicitud.save(update_fields=["estado"])
        crear_notificacion(
            solicitud.cliente, "SOLICITUD",
            f'Tu solicitud "{solicitud.descripcion}" no fue atendida por ningún '
            "trabajador en el tiempo límite.",
            solicitud,
        )
        cerradas += 1

    return {"cerradas": cerradas}


# ------------------------------------------------------------------ 3. Documentos
def avisar_vencimiento_documentos():
    """Avisa a los trabajadores cuyo documento venció o está por vencer."""
    hoy = timezone.localdate()
    aviso = hoy + timedelta(days=settings.DIAS_AVISO_DOCUMENTO)
    trabajadores = Usuario.objects.filter(
        rol=Rol.TRABAJADOR, fecha_vencimiento_documento__isnull=False
    )

    vencidos = 0
    por_vencer = 0
    for trabajador in trabajadores:
        vence = trabajador.fecha_vencimiento_documento
        if vence < hoy:
            crear_notificacion(
                trabajador, "DOCUMENTO",
                f"Tu documento de identidad venció el {vence:%d/%m/%Y}. "
                "Actualízalo para continuar trabajando.",
            )
            vencidos += 1
        elif vence <= aviso:
            crear_notificacion(
                trabajador, "DOCUMENTO",
                f"Tu documento de identidad vence el {vence:%d/%m/%Y}. "
                "Actualízalo para evitar bloqueos.",
            )
            por_vencer += 1

    return {"vencidos": vencidos, "por_vencer": por_vencer}


# ------------------------------------------------------------------ 4. Reportes
def suspender_cuentas_con_reportes():
    """Suspende a quien acumula demasiados reportes de seguridad sin resolver."""
    umbral = settings.UMBRAL_REPORTES_SUSPENSION
    conteo = (
        ReporteSeguridad.objects.filter(estado=ReporteSeguridad.Estado.EN_REVISION)
        .values("reportado")
        .annotate(total=Count("id"))
    )
    administradores = list(Usuario.objects.filter(rol=Rol.ADMINISTRADOR))

    suspendidas = 0
    for fila in conteo:
        if fila["total"] < umbral:
            continue

        usuario = Usuario.objects.filter(pk=fila["reportado"]).first()
        if usuario is None or usuario.bloqueado:
            continue

        usuario.bloqueado = True
        usuario.save(update_fields=["bloqueado"])
        crear_notificacion(
            usuario, "SEGURIDAD",
            f"Tu cuenta fue suspendida temporalmente por acumular "
            f"{fila['total']} reportes de seguridad.",
        )
        for administrador in administradores:
            crear_notificacion(
                administrador, "SEGURIDAD",
                f"La cuenta de {usuario.nombre} ({usuario.correo}) fue suspendida "
                "por superar el umbral de reportes.",
            )
        suspendidas += 1

    return {"suspendidas": suspendidas}


# ------------------------------------------------------------------ 5. Calificaciones
def recordar_calificaciones():
    """Recuerda a los clientes calificar los servicios completados."""
    limite = timezone.now() - timedelta(days=settings.DIAS_RECORDATORIO_CALIFICACION)
    sin_calificar = Solicitud.objects.filter(
        estado=EstadoSolicitud.COMPLETADA,
        calificacion__isnull=True,
        fecha_finalizacion__lt=limite,
    ).select_related("cliente")

    recordados = 0
    for solicitud in sin_calificar:
        crear_notificacion(
            solicitud.cliente, "CALIFICACION",
            f'Aún no calificas el servicio "{solicitud.descripcion}". '
            "Tu valoración ayuda a la comunidad.",
            solicitud,
        )
        recordados += 1

    return {"recordados": recordados}


# ------------------------------------------------------------------ 6 y 7. Suscripciones
def renovar_suscripciones():
    """Cobra la renovación automática de las suscripciones vencidas."""
    return servicio_suscripcion.renovar_vencidas()


def avisar_suscripciones_por_vencer():
    """Avisa a los trabajadores cuya suscripción vence pronto."""
    return servicio_suscripcion.recordar_proximos_a_vencer()


# ------------------------------------------------------------------ 8. Transferencias
def transferir_pagos_netos():
    """Marca como transferidos los pagos que ya se le deben al trabajador."""
    return cobros.transferir_netos()


# ------------------------------------------------------------------ 9. Limpieza
def _esta_en_uso(ruta):
    """True si algún campo del perfil todavía apunta a ese archivo."""
    if not ruta:
        return False
    return Usuario.objects.filter(
        Q(documento=ruta) | Q(selfie=ruta) | Q(foto_perfil=ruta) | Q(documento_legal=ruta)
    ).exists()


def _borrar_si_no_esta_en_uso(campo):
    """Borra el archivo físico si ya nadie lo referencia. Devuelve 1 o 0."""
    if not campo or not campo.name or _esta_en_uso(campo.name):
        return 0
    try:
        campo.delete(save=False)
        return 1
    except OSError:
        return 0


def limpiar_archivos_obsoletos():
    """Borra archivos viejos o que ya no están vigentes.

    Los registros se conservan (sirven de auditoría); solo se elimina el archivo
    físico. Nunca se borra un archivo que todavía use el perfil de un usuario.
    """
    limite = timezone.now() - timedelta(days=settings.DIAS_RETENCION_ARCHIVOS)

    borrados = 0
    for version in DocumentoVersion.objects.all():
        if not version.vigente or version.fecha < limite:
            borrados += _borrar_si_no_esta_en_uso(version.archivo)

    for archivo in Archivo.objects.filter(Q(vigente=False) | Q(fecha__lt=limite)):
        borrados += _borrar_si_no_esta_en_uso(archivo.archivo)

    return {"borrados": borrados}


# ------------------------------------------------------------------ Registro de tareas
TAREAS = {
    "reasignar": ("Reasignar solicitudes sin respuesta", reasignar_solicitudes_sin_respuesta),
    "cerrar-no-atendidas": ("Cerrar solicitudes no atendidas", cerrar_solicitudes_no_atendidas),
    "avisar-documentos": ("Avisar vencimiento de documentos", avisar_vencimiento_documentos),
    "suspender-reportadas": ("Suspender cuentas con reportes", suspender_cuentas_con_reportes),
    "recordar-calificaciones": ("Recordar calificaciones", recordar_calificaciones),
    "renovar-suscripciones": ("Renovar suscripciones", renovar_suscripciones),
    "avisar-suscripciones": ("Avisar suscripciones por vencer", avisar_suscripciones_por_vencer),
    "transferir-pagos": ("Transferir pagos a trabajadores", transferir_pagos_netos),
    "limpiar-archivos": ("Limpiar archivos obsoletos", limpiar_archivos_obsoletos),
}


def ejecutar(nombre):
    """Ejecuta una tarea por su nombre y devuelve (etiqueta, resultado)."""
    etiqueta, funcion = TAREAS[nombre]
    return etiqueta, funcion()
