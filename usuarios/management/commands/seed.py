"""Crea usuarios de ejemplo para probar Cambell sin registrarlos a mano.

Uso:
    python manage.py seed

Crea una cuenta por rol (todas con la misma estructura de correo y contraseña).
Es solo para desarrollo: no lo ejecutes en producción.
"""
from datetime import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from usuarios.models import (
    CoberturaTrabajador,
    EstadoVerificacion,
    Horario,
    Rol,
    Usuario,
    Verificacion,
)

# (correo, contraseña, nombre, rol, datos extra)
USUARIOS_DEMO = [
    {
        "correo": "admin@cambell.com",
        "password": "Admin1234",
        "nombre": "Administrador Cambell",
        "rol": Rol.ADMINISTRADOR,
        "es_superuser": True,
        "telefono": "3000000001",
    },
    {
        "correo": "cliente@cambell.com",
        "password": "Cliente1234",
        "nombre": "Cliente de Prueba",
        "rol": Rol.CLIENTE,
        "telefono": "3000000002",
        "localidad": "Chapinero",
        "barrio": "Marly",
    },
    {
        "correo": "trabajador@cambell.com",
        "password": "Trabajador1234",
        "nombre": "Trabajador de Prueba",
        "rol": Rol.TRABAJADOR,
        "telefono": "3000000003",
        "localidad": "Suba",
        "barrio": "Niza",
        "oficio": "Plomería",
        "anios_experiencia": 5,
        "tarifa_hora": 25000,
        "cuenta_bancaria": "Banco Demo - Ahorros 000111",
        "numero_documento": "1000000001",
    },
    {
        "correo": "electricista@cambell.com",
        "password": "Trabajador1234",
        "nombre": "Electricista de Prueba",
        "rol": Rol.TRABAJADOR,
        "telefono": "3000000004",
        "localidad": "Chapinero",
        "barrio": "Chicó",
        "oficio": "Electricidad",
        "anios_experiencia": 8,
        "tarifa_hora": 30000,
        "cuenta_bancaria": "Banco Demo - Ahorros 000222",
        "numero_documento": "1000000002",
    },
    {
        "correo": "carpintero@cambell.com",
        "password": "Trabajador1234",
        "nombre": "Carpintero de Prueba",
        "rol": Rol.TRABAJADOR,
        "telefono": "3000000005",
        "localidad": "Usaquén",
        "barrio": "Cedritos",
        "oficio": "Carpintería",
        "anios_experiencia": 3,
        "tarifa_hora": 22000,
        "cuenta_bancaria": "Banco Demo - Ahorros 000333",
        "numero_documento": "1000000003",
    },
    {
        "correo": "aliado@cambell.com",
        "password": "Aliado1234",
        "nombre": "Aliado de Prueba",
        "rol": Rol.ALIADO_COMERCIAL,
        "telefono": "3000000006",
        "localidad": "Chapinero",
        "barrio": "Centro",
        "razon_social": "Ferretería Demo SAS",
        "nit": "900999001",
        "tipo_aliado": "Ferretería",
        "direccion_negocio": "Calle 10 # 20-30",
    },
]

# Cobertura de los trabajadores demo (localidades y especialidades).
COBERTURAS = {
    "trabajador@cambell.com": {
        "localidades": ["Suba", "Engativá"],
        "categorias": ["PLOMERIA"],
        "radio_km": 10,
    },
    "electricista@cambell.com": {
        "localidades": ["Chapinero", "Usaquén"],
        "categorias": ["ELECTRICIDAD"],
        "radio_km": 8,
    },
    "carpintero@cambell.com": {
        "localidades": ["Usaquén", "Suba"],
        "categorias": ["CARPINTERIA"],
        "radio_km": 12,
    },
}


class Command(BaseCommand):
    help = "Crea usuarios de ejemplo (admin, cliente, trabajadores y aliado)."

    def handle(self, *args, **options):
        for datos in USUARIOS_DEMO:
            datos = datos.copy()
            correo = datos["correo"]
            password = datos.pop("password")
            es_superuser = datos.pop("es_superuser", False)

            usuario, creado = Usuario.objects.update_or_create(
                correo=correo,
                defaults={
                    **datos,
                    "estado_verificacion": EstadoVerificacion.APROBADO,
                    "debe_cambiar_password": False,
                    "bloqueado": False,
                    "is_superuser": es_superuser,
                },
            )
            # La contraseña se guarda siempre cifrada (nunca en texto plano).
            usuario.set_password(password)
            usuario.save()

            if usuario.rol == Rol.TRABAJADOR:
                cobertura = COBERTURAS.get(correo, {})
                CoberturaTrabajador.objects.update_or_create(
                    trabajador=usuario,
                    defaults={
                        "radio_km": cobertura.get("radio_km", 10),
                        "localidades": cobertura.get("localidades", []),
                        "categorias": cobertura.get("categorias", []),
                        "disponible": True,
                    },
                )

                # Disponibilidad de ejemplo: lunes a viernes, 8:00 a 18:00.
                for dia in range(5):
                    Horario.objects.update_or_create(
                        trabajador=usuario,
                        dia_semana=dia,
                        hora_inicio=time(8, 0),
                        hora_fin=time(18, 0),
                        defaults={"activo": True},
                    )

                # Expediente de verificacion aprobado para poder probar el perfil.
                Verificacion.objects.get_or_create(
                    trabajador=usuario,
                    origen=Verificacion.Origen.MANUAL,
                    defaults={
                        "estado": Verificacion.Estado.APROBADA,
                        "motivo": "Verificación de ejemplo para desarrollo.",
                        "fecha_decision": timezone.now(),
                    },
                )

            estado = "creado" if creado else "actualizado"
            self.stdout.write(self.style.SUCCESS(f"{estado}: {correo} ({usuario.rol})"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Cuentas de ejemplo listas:"))
        self.stdout.write("  admin@cambell.com / Admin1234")
        self.stdout.write("  cliente@cambell.com / Cliente1234")
        self.stdout.write("  trabajador@cambell.com / Trabajador1234")
        self.stdout.write("  electricista@cambell.com / Trabajador1234")
        self.stdout.write("  carpintero@cambell.com / Trabajador1234")
        self.stdout.write("  aliado@cambell.com / Aliado1234")
