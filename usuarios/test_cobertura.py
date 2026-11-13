"""Pruebas de la Fase 1D: compatibilidad de cobertura y distancia (Haversine).

Se prueba la lógica que usa el patrón Observer para avisar a los trabajadores
compatibles y que después reutilizará el motor de recomendación de la Fase 2.
"""
from datetime import datetime, time

from django.test import TestCase
from django.utils import timezone

from solicitudes.models import CategoriaServicio, EstadoSolicitud, Solicitud

from .cobertura import (
    centro_localidad,
    coordenadas_de_barrio,
    distancia_de_trabajador,
    distancia_km,
    es_compatible,
    trabajadores_compatibles,
    trabajadores_compatibles_por_cercania,
)
from .models import CoberturaTrabajador, EstadoVerificacion, Horario, Rol, Usuario

# Lunes 9 de noviembre de 2026, 10:00 a.m. (hora de Bogotá).
LUNES_10 = timezone.make_aware(datetime(2026, 11, 9, 10, 0))
LUNES_15 = timezone.make_aware(datetime(2026, 11, 9, 15, 0))
LUNES_20 = timezone.make_aware(datetime(2026, 11, 9, 20, 0))
MARTES_10 = timezone.make_aware(datetime(2026, 11, 10, 10, 0))


def crear_usuario(correo, rol=Rol.TRABAJADOR, **extra):
    return Usuario.objects.create_user(
        correo, "Clave1234", nombre=correo.split("@")[0], rol=rol, **extra
    )


def crear_trabajador(correo, aprobado=True, bloqueado=False, **extra):
    return crear_usuario(
        correo,
        estado_verificacion=(
            EstadoVerificacion.APROBADO if aprobado else EstadoVerificacion.PENDIENTE
        ),
        bloqueado=bloqueado,
        **extra,
    )


def crear_solicitud(cliente, **extra):
    datos = {
        "descripcion": "Arreglar una fuga",
        "categoria": CategoriaServicio.PLOMERIA,
        "localidad": "Chapinero",
        "barrio": "Marly",
        "precio_ofertado": 50000,
        "estado": EstadoSolicitud.PENDIENTE,
    }
    datos.update(extra)
    return Solicitud.objects.create(cliente=cliente, **datos)


def crear_cobertura(trabajador, **extra):
    datos = {
        "radio_km": 10,
        "localidades": ["Chapinero"],
        "categorias": [CategoriaServicio.PLOMERIA],
        "disponible": True,
        "hora_inicio": time(8, 0),
        "hora_fin": time(18, 0),
    }
    datos.update(extra)
    return CoberturaTrabajador.objects.create(trabajador=trabajador, **datos)


class DistanciaTests(TestCase):
    def test_distancia_entre_el_mismo_punto_es_cero(self):
        self.assertEqual(distancia_km(4.6455, -74.0594, 4.6455, -74.0594), 0)

    def test_distancia_entre_marly_y_niza(self):
        # Marly (Chapinero) y Niza (Suba) están a unos 8,7 km en línea recta.
        distancia = distancia_km(4.6455, -74.0594, 4.7210, -74.0800)
        self.assertGreater(distancia, 8)
        self.assertLess(distancia, 10)

    def test_coordenadas_del_catalogo(self):
        self.assertEqual(coordenadas_de_barrio("Chapinero", "Marly"), (4.6455, -74.0594))
        self.assertIsNone(coordenadas_de_barrio("Chapinero", "No existe"))
        self.assertIsNone(coordenadas_de_barrio("No existe", "Marly"))
        self.assertIsNotNone(centro_localidad("Suba"))
        self.assertIsNone(centro_localidad("No existe"))


class CompatibilidadTests(TestCase):
    def setUp(self):
        self.cliente = crear_usuario("cliente@example.com", Rol.CLIENTE)
        self.solicitud = crear_solicitud(self.cliente)
        self.trabajador = crear_trabajador("trabajador@example.com")
        self.cobertura = crear_cobertura(self.trabajador)

    def test_trabajador_compatible_por_zona_y_oficio(self):
        self.assertTrue(es_compatible(self.solicitud, self.cobertura, LUNES_10))

    def test_no_disponible_no_es_compatible(self):
        self.cobertura.disponible = False
        self.cobertura.save(update_fields=["disponible"])
        self.assertFalse(es_compatible(self.solicitud, self.cobertura, LUNES_10))

    def test_fuera_de_la_ventana_horaria_no_es_compatible(self):
        self.assertFalse(es_compatible(self.solicitud, self.cobertura, LUNES_20))

    def test_sin_especialidades_atiende_todas(self):
        self.cobertura.categorias = []
        self.cobertura.save(update_fields=["categorias"])
        self.assertTrue(es_compatible(self.solicitud, self.cobertura, LUNES_10))

    def test_otra_especialidad_no_es_compatible(self):
        self.cobertura.categorias = [CategoriaServicio.ELECTRICIDAD]
        self.cobertura.save(update_fields=["categorias"])
        self.assertFalse(es_compatible(self.solicitud, self.cobertura, LUNES_10))

    def test_otra_localidad_fuera_del_radio_no_es_compatible(self):
        self.cobertura.localidades = ["Suba"]
        self.cobertura.radio_km = 1
        self.cobertura.save(update_fields=["localidades", "radio_km"])
        self.assertFalse(es_compatible(self.solicitud, self.cobertura, LUNES_10))

    def test_otra_localidad_dentro_del_radio_es_compatible(self):
        self.cobertura.localidades = ["Suba"]
        self.cobertura.radio_km = 30
        self.cobertura.save(update_fields=["localidades", "radio_km"])
        self.assertTrue(es_compatible(self.solicitud, self.cobertura, LUNES_10))

    def test_sin_localidades_cubre_cualquier_zona(self):
        self.cobertura.localidades = []
        self.cobertura.save(update_fields=["localidades"])
        self.assertTrue(es_compatible(self.solicitud, self.cobertura, LUNES_10))

    def test_los_bloques_de_horario_mandan_sobre_la_ventana_general(self):
        # La ventana general dice 8:00-18:00, pero el bloque real es 14:00-18:00.
        Horario.objects.create(
            trabajador=self.trabajador,
            dia_semana=Horario.Dia.LUNES,
            hora_inicio=time(14, 0),
            hora_fin=time(18, 0),
        )
        self.assertFalse(es_compatible(self.solicitud, self.cobertura, LUNES_10))
        self.assertTrue(es_compatible(self.solicitud, self.cobertura, LUNES_15))
        self.assertFalse(es_compatible(self.solicitud, self.cobertura, MARTES_10))

    def test_un_bloque_inactivo_no_cuenta(self):
        Horario.objects.create(
            trabajador=self.trabajador,
            dia_semana=Horario.Dia.LUNES,
            hora_inicio=time(14, 0),
            hora_fin=time(18, 0),
            activo=False,
        )
        # Al no haber bloques activos se usa la ventana general (8:00-18:00).
        self.assertTrue(es_compatible(self.solicitud, self.cobertura, LUNES_10))

    def test_bloque_que_cubre_el_dia_y_la_hora(self):
        bloque = Horario.objects.create(
            trabajador=self.trabajador,
            dia_semana=Horario.Dia.LUNES,
            hora_inicio=time(8, 0),
            hora_fin=time(12, 0),
        )
        self.assertTrue(bloque.cubre(LUNES_10))
        self.assertFalse(bloque.cubre(MARTES_10))


class TrabajadoresCompatiblesTests(TestCase):
    def setUp(self):
        self.cliente = crear_usuario("cliente@example.com", Rol.CLIENTE)
        self.solicitud = crear_solicitud(self.cliente)

        self.cerca = crear_trabajador("cerca@example.com")
        crear_cobertura(self.cerca, localidades=["Chapinero"])

        self.lejos = crear_trabajador("lejos@example.com")
        crear_cobertura(self.lejos, localidades=["Suba"], radio_km=30)

        self.otro_oficio = crear_trabajador("electricista@example.com")
        crear_cobertura(
            self.otro_oficio, categorias=[CategoriaServicio.ELECTRICIDAD]
        )

        self.no_disponible = crear_trabajador("ocupado@example.com")
        crear_cobertura(self.no_disponible, disponible=False)

        self.sin_verificar = crear_trabajador("nuevo@example.com", aprobado=False)
        crear_cobertura(self.sin_verificar)

        self.bloqueado = crear_trabajador("bloqueado@example.com", bloqueado=True)
        crear_cobertura(self.bloqueado)

    def test_solo_incluye_aprobados_disponibles_y_compatibles(self):
        compatibles = trabajadores_compatibles(self.solicitud, LUNES_10)
        self.assertCountEqual(compatibles, [self.cerca, self.lejos])

    def test_ordena_del_mas_cercano_al_mas_lejano(self):
        compatibles = trabajadores_compatibles_por_cercania(self.solicitud, LUNES_10)
        self.assertEqual(compatibles, [self.cerca, self.lejos])

    def test_distancia_usa_la_cobertura(self):
        distancia_cerca = distancia_de_trabajador(
            self.solicitud, self.cerca, self.cerca.cobertura
        )
        distancia_lejos = distancia_de_trabajador(
            self.solicitud, self.lejos, self.lejos.cobertura
        )
        self.assertLess(distancia_cerca, distancia_lejos)

    def test_distancia_usa_la_localidad_del_perfil_si_no_hay_cobertura(self):
        self.cerca.localidad = "Chapinero"
        self.cerca.save(update_fields=["localidad"])
        self.assertGreater(
            distancia_de_trabajador(self.solicitud, self.cerca, cobertura=None), 0
        )

    def test_usa_las_coordenadas_guardadas_en_la_solicitud(self):
        # Coordenadas cerca de Suba: con un radio corto desde Chapinero ya no cubre.
        self.solicitud.localidad = "Suba"
        self.solicitud.barrio = "Niza"
        self.solicitud.latitud = 4.7210
        self.solicitud.longitud = -74.0800
        self.solicitud.save(
            update_fields=["localidad", "barrio", "latitud", "longitud"]
        )
        self.cerca.cobertura.radio_km = 1
        self.cerca.cobertura.save(update_fields=["radio_km"])
        self.assertFalse(es_compatible(self.solicitud, self.cerca.cobertura, LUNES_10))
