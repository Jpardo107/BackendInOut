from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from user.models import PersonalEmpresa
from user.services.instalacion_matcher import (
    buscar_instalacion,
    construir_indice_instalaciones,
)


class Command(BaseCommand):
    help = "Vincula personas sin instalación usando la ubicación importada desde Excel."

    def add_arguments(self, parser):
        parser.add_argument(
            "--aplicar",
            action="store_true",
            help="Guarda las relaciones. Sin esta opción solo muestra una vista previa.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        aplicar = options["aplicar"]
        indice = construir_indice_instalaciones()
        pendientes = Counter()
        vinculaciones = []

        personas = PersonalEmpresa.objects.filter(instalacion__isnull=True).order_by("id")
        for persona in personas:
            instalacion = buscar_instalacion(persona.ubicacion, indice)
            if instalacion:
                vinculaciones.append((persona, instalacion))
            else:
                pendientes[persona.ubicacion or "SIN UBICACION"] += 1

        if aplicar:
            for persona, instalacion in vinculaciones:
                persona.instalacion = instalacion
                persona.save(update_fields=["instalacion", "actualizado_en"])
        modo = "APLICADO" if aplicar else "VISTA PREVIA"
        self.stdout.write(self.style.SUCCESS(f"{modo}: {len(vinculaciones)} persona(s) vinculable(s)."))
        self.stdout.write(
            f"Ya vinculadas y preservadas: "
            f"{PersonalEmpresa.objects.exclude(instalacion__isnull=True).count()}"
        )
        self.stdout.write(f"Sin coincidencia: {sum(pendientes.values())}")

        if pendientes:
            self.stdout.write("Ubicaciones pendientes:")
            for ubicacion, total in pendientes.most_common():
                self.stdout.write(f"  {total:>3}  {ubicacion}")
