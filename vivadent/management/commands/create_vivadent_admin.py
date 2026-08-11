from django.core.management.base import BaseCommand, CommandError
from user.models import Usuario
from vivadent.models import VivadentAccess


class Command(BaseCommand):
    help = "Crea o actualiza una cuenta aislada para el administrador Vivadent."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("email")
        parser.add_argument("--password", required=True)
        parser.add_argument("--nombres", default="Administrador")
        parser.add_argument("--apellidos", default="Vivadent")
        parser.add_argument("--rut", required=True)

    def handle(self, *args, **options):
        if len(options["password"]) < 10:
            raise CommandError("La contraseña debe tener al menos 10 caracteres.")
        user, created = Usuario.objects.get_or_create(username=options["username"], defaults={"email": options["email"], "nombres": options["nombres"], "apellidos": options["apellidos"], "rut": options["rut"]})
        user.email, user.nombres, user.apellidos = options["email"], options["nombres"], options["apellidos"]
        user.is_staff = user.is_superuser = False
        user.set_password(options["password"])
        user.save()
        VivadentAccess.objects.update_or_create(user=user, defaults={"active": True})
        self.stdout.write(self.style.SUCCESS(f"Cuenta Vivadent {'creada' if created else 'actualizada'}: {user.username}"))
