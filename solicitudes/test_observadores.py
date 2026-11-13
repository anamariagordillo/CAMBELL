"""Pruebas de la Fase 1D: patrón Observer de las solicitudes.

Comprueba que los eventos avisan a quien corresponde: las solicitudes nuevas o
reasignadas se ofrecen a los trabajadores compatibles (ordenados por cercanía),
el cliente recibe el estado y la calificación recalcula el promedio.
"""
from datetime import time

from django.test import TestCase

from mensajeria.models import Notificacion
from usuarios.models import CoberturaTrabajador, EstadoVerificacion, Rol, Usuario

from . import servicios
from .models import CategoriaServicio, EstadoSolicitud, Solicitud
from .observadores import EventoSolicitud, TipoEvento, notificador


def crear_usuario(correo, rol, **extra):
    return Usuario.objects.create_user(
        correo, "Clave1234", nombre=correo.split("@")[0], rol=rol, **extra
    )


def crear_trabajador(correo, **extra):
    return crear_usuario(
        correo,
        Rol.TRABAJADOR,
        estado_verificacion=EstadoVerificacion.APROBADO,
        **extra,
    )


def crear_cobertura(trabajador, localidades=None, radio_km=10, categorias=None, **extra):
    return CoberturaTrabajador.objects.create(
        trabajador=trabajador,
        radio_km=radio_km,
        localidades=localidades or ["Chapinero"],
        categorias=categorias or [CategoriaServicio.PLOMERIA],
        # Ventana amplia: los avisos del Observer usan la hora real del sistema.
        hora_inicio=time(0, 0),
        hora_fin=time(23, 59),
        **extra,
    )


class ObserverSolicitudTests(TestCase):
    def setUp(self):
        self.cliente = crear_usuario("cliente@example.com", Rol.CLIENTE)

        self.cerca = crear_trabajador("cerca@example.com")
        crear_cobertura(self.cerca, localidades=["Chapinero"])

        self.lejos = crear_trabajador("lejos@example.com")
        crear_cobertura(self.lejos, localidades=["Suba"], radio_km=30)

        self.otro_oficio = crear_trabajador("electricista@example.com")
        crear_cobertura(
            self.otro_oficio,
            localidades=["Chapinero"],
            radio_km=30,
            categorias=[CategoriaServicio.ELECTRICIDAD],
        )

        self.no_disponible = crear_trabajador("ocupado@example.com")
        crear_cobertura(self.no_disponible, disponible=False)

        self.sin_verificar = crear_usuario(
            "nuevo@example.com",
            Rol.TRABAJADOR,
            estado_verificacion=EstadoVerificacion.PENDIENTE,
        )
        crear_cobertura(self.sin_verificar)

    def nueva_solicitud(self):
        return servicios.crear_solicitud(
            self.cliente,
            descripcion="Arreglar una fuga",
            categoria=CategoriaServicio.PLOMERIA,
            localidad="Chapinero",
            barrio="Marly",
            precio_ofertado=50000,
        )

    def avisos(self):
        return Notificacion.objects.filter(tipo="ASIGNACION").order_by("id")

    def test_crear_avisa_solo_a_los_compatibles(self):
        solicitud = self.nueva_solicitud()
        destinatarios = [n.usuario for n in self.avisos()]

        self.assertIn(self.cerca, destinatarios)
        self.assertIn(self.lejos, destinatarios)
        self.assertNotIn(self.otro_oficio, destinatarios)
        self.assertNotIn(self.no_disponible, destinatarios)
        self.assertNotIn(self.sin_verificar, destinatarios)
        self.assertEqual(len(destinatarios), 2)
        self.assertTrue(all(n.solicitud == solicitud for n in self.avisos()))

    def test_crear_avisa_primero_al_mas_cercano(self):
        self.nueva_solicitud()
        self.assertEqual(
            [n.usuario for n in self.avisos()], [self.cerca, self.lejos]
        )

    def test_el_aviso_menciona_zona_y_precio(self):
        self.nueva_solicitud()
        aviso = self.avisos().filter(usuario=self.cerca).get()
        self.assertIn("Marly, Chapinero, Bogotá", aviso.mensaje)
        self.assertIn("50,000", aviso.mensaje)

    def test_reasignar_vuelve_a_avisar(self):
        solicitud = self.nueva_solicitud()
        Notificacion.objects.all().delete()

        notificador.notificar(EventoSolicitud(TipoEvento.REASIGNADA, solicitud))
        self.assertEqual(self.avisos().count(), 2)

    def test_aceptar_avisa_al_cliente(self):
        solicitud = self.nueva_solicitud()
        Notificacion.objects.all().delete()

        servicios.aceptar(solicitud.id, self.cerca)
        aviso = Notificacion.objects.get(usuario=self.cliente, tipo="ESTADO")
        self.assertIn("fue aceptada", aviso.mensaje)
        self.assertIn(self.cerca.nombre, aviso.mensaje)

    def test_completar_avisa_al_cliente(self):
        solicitud = self.nueva_solicitud()
        Notificacion.objects.all().delete()
        solicitud.estado = EstadoSolicitud.COMPLETADA
        solicitud.save(update_fields=["estado"])

        notificador.notificar(EventoSolicitud(TipoEvento.COMPLETADA, solicitud))
        aviso = Notificacion.objects.get(usuario=self.cliente, tipo="ESTADO")
        self.assertIn("No olvides calificar", aviso.mensaje)

    def test_calificar_recalcula_el_promedio_del_trabajador(self):
        solicitud = self.nueva_solicitud()
        servicios.aceptar(solicitud.id, self.cerca)
        solicitud.refresh_from_db()
        solicitud.estado = EstadoSolicitud.COMPLETADA
        solicitud.save(update_fields=["estado"])

        otra = self.nueva_solicitud()
        servicios.aceptar(otra.id, self.cerca)
        otra.refresh_from_db()
        otra.estado = EstadoSolicitud.COMPLETADA
        otra.save(update_fields=["estado"])

        solicitud.calificacion = 5
        solicitud.save(update_fields=["calificacion"])
        notificador.notificar(EventoSolicitud(TipoEvento.CALIFICADA, solicitud))

        otra.calificacion = 3
        otra.save(update_fields=["calificacion"])
        notificador.notificar(EventoSolicitud(TipoEvento.CALIFICADA, otra))

        self.cerca.refresh_from_db()
        self.assertAlmostEqual(self.cerca.calificacion_promedio, 4.0)
        self.assertEqual(self.cerca.total_calificaciones, 2)
