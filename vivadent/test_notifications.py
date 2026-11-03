import io
import uuid
from datetime import timedelta
from unittest.mock import patch
from urllib.error import HTTPError

from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .models import AnalyticsEvent, TelegramDispatch, VisitNotification
from .notifications import TelegramUnavailable, deliver_one, send_text, telegram


CONFIG = dict(VIVADENT_TELEGRAM_ENABLED=True, VIVADENT_TELEGRAM_BOT_TOKEN='fake-test-token',
              VIVADENT_TELEGRAM_CHAT_ID='123', VIVADENT_TELEGRAM_ALLOWED_ORIGINS='https://clinicasvivadent.cl')


@override_settings(**CONFIG)
class VisitNotificationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.client.credentials(HTTP_ORIGIN='https://clinicasvivadent.cl', HTTP_USER_AGENT='Mozilla/5.0')

    def visit(self, session='test-session', **extra):
        return self.client.post('/api/vivadent/public/events/', {
            'event_type': 'page_view', 'event_id': str(uuid.uuid4()), 'session_id': session,
            'path': '/', 'device': 'mobile', 'source': 'direct', **extra}, format='json')

    def test_reloads_and_navigation_create_one_notice_per_session(self):
        self.assertEqual(self.visit().status_code, 201)
        self.assertEqual(self.visit(path='/promociones').status_code, 201)
        self.assertEqual(self.visit(session='another-session').status_code, 201)
        self.assertEqual(VisitNotification.objects.count(), 2)
        self.assertEqual(AnalyticsEvent.objects.count(), 3)

    def test_duplicate_event_does_not_enqueue_again(self):
        event_id = str(uuid.uuid4())
        self.visit(event_id=event_id)
        self.visit(session='another', event_id=event_id)
        self.assertEqual(VisitNotification.objects.count(), 1)
        self.assertEqual(AnalyticsEvent.objects.count(), 1)

    def test_ignores_bots_dnt_foreign_origins_and_non_page_events(self):
        for headers in [dict(HTTP_USER_AGENT='Googlebot'), dict(HTTP_DNT='1'),
                        dict(HTTP_ORIGIN='https://untrusted.example')]:
            self.client.credentials(HTTP_ORIGIN='https://clinicasvivadent.cl', HTTP_USER_AGENT='Mozilla/5.0')
            self.client._credentials.update(headers)
            self.assertEqual(self.visit().status_code, 201)
        self.client.credentials(HTTP_ORIGIN='https://clinicasvivadent.cl', HTTP_USER_AGENT='Mozilla/5.0')
        self.visit(event_type='checkout_started')
        self.assertEqual(VisitNotification.objects.count(), 0)
        self.assertEqual(AnalyticsEvent.objects.count(), 4)

    @override_settings(VIVADENT_TELEGRAM_ENABLED=False)
    def test_disabled_does_not_create_notices(self):
        self.assertEqual(self.visit().status_code, 201)
        self.assertFalse(VisitNotification.objects.exists())

    def test_notice_does_not_include_arbitrary_urls_or_treatments(self):
        self.visit(path='/promociones/implante?email=private@example.com', source='secret.example.com')
        notice = VisitNotification.objects.get()
        self.assertEqual(notice.path, '/promociones/[tratamiento]')
        self.assertEqual(notice.source, 'Otra web')

    def test_queue_failure_does_not_lose_analytics(self):
        with patch('vivadent.notifications.VisitNotification.objects.get_or_create', side_effect=DatabaseError('test')):
            self.assertEqual(self.visit().status_code, 201)
        self.assertEqual(AnalyticsEvent.objects.count(), 1)

    def test_status_is_read_only_and_does_not_expose_token(self):
        output = io.StringIO()
        with patch('vivadent.notifications.urlopen') as network:
            call_command('vivadent_telegram', '--status', stdout=output)
        network.assert_not_called()
        self.assertNotIn('fake-test-token', output.getvalue())


@override_settings(**CONFIG)
class TelegramDeliveryTests(TransactionTestCase):
    def notice(self):
        return VisitNotification.objects.create(session_id=str(uuid.uuid4()), path='/', source='Directa',
                                                device='mobile', next_at=timezone.now())

    def unlock(self):
        TelegramDispatch.objects.update(next_send_at=timezone.now()-timedelta(seconds=1))

    @patch('vivadent.notifications.send_text')
    def test_public_event_dispatches_after_database_commit(self, send):
        cache.clear()
        client = APIClient()
        response = client.post('/api/vivadent/public/events/', {
            'event_type': 'page_view', 'session_id': 'committed-session', 'path': '/',
        }, format='json', HTTP_USER_AGENT='Mozilla/5.0', HTTP_ORIGIN='https://clinicasvivadent.cl')
        self.assertEqual(response.status_code, 201)
        send.assert_called_once()
        self.assertIsNotNone(VisitNotification.objects.get().sent_at)

    @patch('vivadent.notifications.send_text')
    def test_success_sends_once_and_never_before_commit(self, send):
        notice = self.notice()
        with transaction.atomic():
            self.assertFalse(deliver_one())
        send.assert_not_called()
        self.assertTrue(deliver_one())
        notice.refresh_from_db()
        self.assertIsNotNone(notice.sent_at)
        self.unlock()
        self.assertFalse(deliver_one())
        send.assert_called_once()

    @patch('vivadent.notifications.send_text')
    def test_provider_failure_retries_without_marking_sent(self, send):
        notice = self.notice()
        send.side_effect = TelegramUnavailable(120)
        before = timezone.now()
        self.assertFalse(deliver_one())
        notice.refresh_from_db()
        self.assertIsNone(notice.sent_at)
        self.assertGreaterEqual(notice.next_at, before+timedelta(seconds=120))
        self.assertEqual(notice.attempts, 1)
        self.assertFalse(deliver_one())
        send.assert_called_once()
        self.unlock()
        VisitNotification.objects.update(next_at=timezone.now())
        send.side_effect = None
        self.assertTrue(deliver_one())
        notice.refresh_from_db()
        self.assertEqual(notice.attempts, 2)

    @patch('vivadent.notifications.send_text')
    def test_active_lease_and_old_visits_are_skipped(self, send):
        self.notice()
        TelegramDispatch.objects.create(pk=1, next_send_at=timezone.now()+timedelta(seconds=30), lease='other-worker')
        self.assertFalse(deliver_one())
        self.unlock()
        VisitNotification.objects.update(created_at=timezone.now()-timedelta(hours=25))
        self.assertFalse(deliver_one())
        send.assert_not_called()

    @patch('vivadent.notifications.telegram', return_value={'message_id': 123})
    def test_api_payload_disables_paid_broadcast_and_link_previews(self, api):
        send_text('Test')
        payload = api.call_args.args[1]
        self.assertFalse(payload['allow_paid_broadcast'])
        self.assertEqual(payload['link_preview_options'], {'is_disabled': True})

    def test_http_rate_limit_is_parsed_without_exposing_credentials(self):
        error = HTTPError('https://api.telegram.org/botfake-test-token/sendMessage', 429,
                          'Rate limited', {}, io.BytesIO(b'{"parameters":{"retry_after":123}}'))
        with patch('vivadent.notifications.urlopen', side_effect=error):
            with self.assertRaises(TelegramUnavailable) as caught:
                telegram('sendMessage', {})
        self.assertEqual(caught.exception.retry_after, 123)
        self.assertNotIn('fake-test-token', str(caught.exception))
