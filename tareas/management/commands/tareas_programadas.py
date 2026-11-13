"""Ejecuta los trabajos programados de Cambell.

Uso:
    python manage.py tareas_programadas                 # todas
    python manage.py tareas_programadas --tarea reasignar
    python manage.py tareas_programadas --listar

En producción se programa con cron (ver README).
"""
from django.core.management.base import BaseCommand, CommandError

from tareas.trabajos import TAREAS, ejecutar


class Command(BaseCommand):
    help = "Ejecuta las tareas programadas (reasignaciones, avisos, limpieza, etc.)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tarea",
            choices=sorted(TAREAS),
            help="Ejecuta solo una tarea. Si se omite, se ejecutan todas.",
        )
        parser.add_argument(
            "--listar",
            action="store_true",
            help="Muestra las tareas disponibles y no ejecuta ninguna.",
        )

    def handle(self, *args, **options):
        if options["listar"]:
            for nombre, (etiqueta, _) in sorted(TAREAS.items()):
                self.stdout.write(f"{nombre}: {etiqueta}")
            return

        nombres = [options["tarea"]] if options["tarea"] else list(TAREAS)
        if not nombres:
            raise CommandError("No hay tareas registradas.")

        for nombre in nombres:
            etiqueta, resultado = ejecutar(nombre)
            self.stdout.write(self.style.SUCCESS(f"✔ {etiqueta}: {resultado}"))
