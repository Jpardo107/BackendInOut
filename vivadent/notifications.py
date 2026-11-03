"""VivaDent visit notifications, adapted from NovaTech's durable Telegram dispatcher."""
import json
import logging
import os
import re
import uuid
from datetime import timedelta
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import TelegramDispatch, VisitNotification

logger = logging.getLogger(__name__)


def setting(name, default=''):
    return getattr(settings, 'VIVADENT_TELEGRAM_' + name, os.getenv('VIVADENT_TELEGRAM_' + name, default))


def enabled():
    return str(setting('ENABLED', False)).strip().lower() in ('true', '1', 'yes')


def configured():
    return enabled() and bool(str(setting('BOT_TOKEN')).strip() and str(setting('CHAT_ID')).strip())


class TelegramUnavailable(Exception):
    def __init__(self, retry_after=60):
        try:
            self.retry_after = min(86400, max(5, int(retry_after)))
        except (ValueError, TypeError):
            self.retry_after = 60
        super().__init__('Telegram no disponible; revisa configuración y acceso del bot al chat.')


def telegram(method, payload):
    url = f'https://api.telegram.org/bot{str(setting("BOT_TOKEN")).strip()}/{method}'
    request = Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=4) as response:
            data = json.loads(response.read(65536))
        if not isinstance(data, dict) or not data.get('ok'):
            raise TelegramUnavailable(data.get('parameters', {}).get('retry_after', 60) if isinstance(data, dict) else 60)
        return data.get('result')
    except HTTPError as error:
        try:
            delay = json.loads(error.read(65536)).get('parameters', {}).get('retry_after', 60)
        except Exception:
            delay = 60
        raise TelegramUnavailable(delay) from None
    except TelegramUnavailable:
        raise
    except Exception:
        # Exceptions from HTTP clients can include the token in their URL.
        raise TelegramUnavailable() from None


def send_text(text):
    result = telegram('sendMessage', {'chat_id': str(setting('CHAT_ID')).strip(), 'text': text,
        'link_preview_options': {'is_disabled': True}, 'allow_paid_broadcast': False})
    if not isinstance(result, dict) or not result.get('message_id'):
        raise TelegramUnavailable()
    return result


def safe_path(value):
    path = urlsplit(value).path
    if path == '/':
        return '/'
    if path.rstrip('/') == '/promociones':
        return '/promociones/'
    # Do not forward arbitrary URL text, patient data, or query strings to Telegram.
    if re.fullmatch(r'/promociones/[a-zA-Z0-9_-]+/?', path):
        return '/promociones/[tratamiento]'
    return '/otra-pagina'


def safe_source(value):
    value = value.lower().strip()
    if value in ('', 'direct'):
        return 'Directa'
    if re.fullmatch(r'([a-z0-9-]+\.)*google\.[a-z.]+', value):
        return 'Google'
    for domain, title in [('instagram.com', 'Instagram'), ('facebook.com', 'Facebook'), ('tiktok.com', 'TikTok')]:
        if value == domain or value.endswith('.' + domain):
            return title
    return 'Otra web'


def deliver_one():
    if not configured() or transaction.get_connection().in_atomic_block:
        return False
    now = timezone.now()
    TelegramDispatch.objects.get_or_create(pk=1, defaults={'next_send_at': now})
    lease = str(uuid.uuid4())
    if not TelegramDispatch.objects.filter(pk=1, next_send_at__lte=now).update(next_send_at=now + timedelta(seconds=30), lease=lease):
        return False
    delay = 1.2
    notice = None
    try:
        notice = VisitNotification.objects.filter(sent_at__isnull=True, next_at__lte=now,
            created_at__gte=now-timedelta(hours=24)).order_by('created_at').first()
        if notice is None:
            return False
        VisitNotification.objects.filter(pk=notice.pk).update(attempts=F('attempts') + 1)
        when = timezone.localtime(notice.created_at, ZoneInfo('America/Santiago')).strftime('%d/%m/%Y %H:%M')
        device = {'mobile': 'Celular', 'tablet': 'Tablet', 'desktop': 'Computador'}.get(notice.device, 'Sin identificar')
        send_text(f'👋 Nueva visita a VivaDent\nPágina: {notice.path}\nOrigen: {notice.source}\nDispositivo: {device}\nHora de Chile: {when}')
        VisitNotification.objects.filter(pk=notice.pk).update(sent_at=timezone.now())
        return True
    except TelegramUnavailable as error:
        delay = error.retry_after
        if notice:
            VisitNotification.objects.filter(pk=notice.pk).update(next_at=timezone.now()+timedelta(seconds=delay))
        logger.warning('Aviso de VivaDent pendiente: Telegram no disponible; se reintentará.')
        return False
    finally:
        TelegramDispatch.objects.filter(pk=1, lease=lease).update(next_send_at=timezone.now()+timedelta(seconds=delay), lease='')


def notify_visit(request, event):
    if not enabled() or event.event_type != 'page_view' or not event.session_id:
        return
    if request.headers.get('DNT') == '1' or request.user.is_authenticated:
        return
    agent = request.headers.get('User-Agent', '').lower()
    if not agent or re.search(r'bot|spider|crawler|headless|preview|curl|wget', agent):
        return
    allowed = str(setting('ALLOWED_ORIGINS', 'https://clinicasvivadent.cl,https://www.clinicasvivadent.cl')).split(',')
    if request.headers.get('Origin', '').rstrip('/') not in [v.strip().rstrip('/') for v in allowed if v.strip()]:
        return
    try:
        # A savepoint keeps optional notification failures from rolling back analytics.
        with transaction.atomic():
            VisitNotification.objects.get_or_create(session_id=event.session_id, defaults={
                'path': safe_path(event.path), 'source': safe_source(event.source),
                'device': event.device if event.device in ('mobile', 'tablet', 'desktop') else '', 'next_at': timezone.now()})
        def flush():
            try:
                deliver_one()
            except Exception:
                logger.warning('No se pudo despachar Telegram de VivaDent; el aviso sigue en la cola.')
        transaction.on_commit(flush)
    except Exception:
        logger.warning('No se pudo preparar Telegram de VivaDent; las métricas se conservaron.')
