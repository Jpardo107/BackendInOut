from django.core.management.base import BaseCommand, CommandError

from supervision.resumen_solicitudes import ahora_chile, debe_enviar_programado, enviar_resumen


class Command(BaseCommand):
    help = (
        "Envía el correo diario de solicitudes de supervisión. Pensado para un cron que corre "
        "a las 10:00 y 11:00 UTC de lunes a viernes: solo envía cuando en Chile son las 07, "
        "así funciona con y sin horario de verano, y nunca envía dos veces el mismo día."
    )

    def add_arguments(self, parser):
        parser.add_argument("--forzar", action="store_true", help="Envía ahora sin revisar día, hora ni envíos previos.")

    def handle(self, *args, forzar, **options):
        ahora = ahora_chile()
        if not forzar:
            debe, motivo = debe_enviar_programado(ahora)
            if not debe:
                self.stdout.write(motivo)
                return
        envio = enviar_resumen(ahora)
        if not envio.enviado:
            raise CommandError(f"No se envió el resumen: {envio.error}")
        self.stdout.write(f"Resumen enviado a {', '.join(envio.destinatarios)} con {envio.cantidad} solicitudes.")
