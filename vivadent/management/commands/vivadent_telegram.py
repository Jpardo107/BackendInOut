import time
from django.core.management.base import BaseCommand, CommandError
from vivadent.notifications import configured, setting, deliver_one, telegram, send_text, TelegramUnavailable


class Command(BaseCommand):
    help = 'Diagnóstico y envío de avisos Telegram de VivaDent. --status nunca envía mensajes.'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--status', action='store_true')
        group.add_argument('--discover', action='store_true')
        group.add_argument('--test', action='store_true')
        group.add_argument('--flush', action='store_true')
        group.add_argument('--watch', action='store_true')

    def handle(self, *args, **options):
        if options['status']:
            from vivadent.models import VisitNotification
            from django.utils import timezone
            from datetime import timedelta
            self.stdout.write(f'Configurado: {configured()}; pendientes recientes: {VisitNotification.objects.filter(sent_at__isnull=True, created_at__gte=timezone.now()-timedelta(hours=24)).count()}')
            for name in ('ENABLED', 'BOT_TOKEN', 'CHAT_ID'):
                self.stdout.write(f'VIVADENT_TELEGRAM_{name}: {"presente" if setting(name) else "ausente"}')
            return
        try:
            if options['discover']:
                if not setting('BOT_TOKEN'):
                    raise CommandError('Falta VIVADENT_TELEGRAM_BOT_TOKEN.')
                updates = telegram('getUpdates', {'timeout': 0, 'limit': 100, 'allowed_updates': ['message']})
                chats = {str(u['message']['chat']['id']) for u in updates or [] if u.get('message', {}).get('chat', {}).get('type') in ('private', 'group', 'supergroup')}
                self.stdout.write('\n'.join(sorted(chats)) if chats else 'Abre el bot y pulsa Iniciar; en un grupo agrégalo y envía un mensaje dirigido al bot.')
                return
            if not configured():
                raise CommandError('Configura VIVADENT_TELEGRAM_ENABLED=true, BOT_TOKEN y CHAT_ID en el backend.')
            if options['test']:
                send_text('✅ VivaDent: conexión de avisos de visitas comprobada.')
                self.stdout.write('Mensaje de prueba enviado.')
                return
            count = 0
            while True:
                delivered = deliver_one()
                count += int(delivered)
                if not options['watch'] and (not delivered or count >= 40):
                    break
                time.sleep(1.3 if delivered else 5)
            self.stdout.write(f'Avisos enviados: {count}')
        except TelegramUnavailable as error:
            raise CommandError(str(error)) from None
