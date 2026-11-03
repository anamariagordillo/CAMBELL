import os
from getpass import getpass

from django.core.management.base import BaseCommand, CommandError

from usuarios.models import Usuario


class Command(BaseCommand):
    help = "Crea el usuario administrador de Cambell (reemplaza al AdminInitializer de Java)."

    def add_arguments(self, parser):
        parser.add_argument("--correo", default="admin@cambell.com")
        parser.add_argument("--nombre", default="Administrador")

    def handle(self, *args, **opciones):
        correo = opciones["correo"].strip().lower()
        if Usuario.objects.filter(correo=correo).exists():
            self.stdout.write(f"Ya existe un usuario con el correo {correo}. No se hizo nada.")
            return

        # La contraseña NO está escrita en el código: viene del entorno o se pide por consola.
        password = os.getenv("CAMBELL_ADMIN_PASSWORD")
        if not password:
            password = getpass("Contraseña para el administrador: ")
            if password != getpass("Repite la contraseña: "):
                raise CommandError("Las contraseñas no coinciden.")
        if len(password) < 8:
            raise CommandError("La contraseña debe tener al menos 8 caracteres.")

        Usuario.objects.create_superuser(correo=correo, password=password, nombre=opciones["nombre"])
        self.stdout.write(self.style.SUCCESS(f"Administrador creado: {correo}"))
