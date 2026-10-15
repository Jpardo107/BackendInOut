from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
from django.utils import timezone
from django.core.cache import cache
from rest_framework.test import APITestCase
from user.models import Usuario
from .models import Promotion, StoreCollection, StoreSession, AnalyticsEvent, VivadentAccess


class CommerceTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = Usuario.objects.create_user(username='commerce', password='Safe123!', nombres='Viva', apellidos='Dent', rut='12345678-5', email='commerce@example.cl')
        VivadentAccess.objects.create(user=self.user)
        self.promo = Promotion.objects.create(title='Limpieza', subtitle='Dental', price='$30.000', description='Limpieza', status='active')
        self.draft = Promotion.objects.create(title='Borrador', subtitle='Dental', price='$10.000', description='Test', status='draft')

    def admin(self):
        self.client.force_authenticate(self.user)

    def test_collection_requires_admin_and_keeps_order_and_empty_selection(self):
        collection = StoreCollection.objects.get(key='tienda')
        url = f'/api/vivadent/collections/{collection.id}/'
        self.assertIn(self.client.patch(url, {'title': 'No'}).status_code, [401, 403])
        self.admin()
        response = self.client.patch(url, {'title': 'Mis favoritos', 'promotion_ids': [self.draft.id, self.promo.id]}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['promotion_ids'], [self.draft.id, self.promo.id])
        self.assertEqual(self.client.patch(url, {'promotion_ids': [999999]}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'promotion_ids': [self.promo.id, self.promo.id]}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'promotion_ids': []}, format='json').status_code, 200)
        self.client.force_authenticate(None)
        content = self.client.get('/api/vivadent/public/content/').data
        self.assertEqual(next(x for x in content['collections'] if x['key'] == 'tienda')['promotion_ids'], [])
        self.assertNotIn(self.draft.id, [x['id'] for x in content['promotions']])

    def test_hidden_collection_and_deleted_promotions(self):
        c = StoreCollection.objects.get(key='facial')
        c.promotion_ids = [self.promo.id]; c.save()
        self.promo.delete()
        self.admin()
        self.assertEqual(self.client.get(f'/api/vivadent/collections/{c.id}/').data['promotion_ids'], [])
        c.enabled = False; c.save()
        self.assertFalse(next(x for x in self.client.get('/api/vivadent/public/content/').data['collections'] if x['key'] == 'facial')['enabled'])

    def test_events_deduplicated_and_client_cannot_claim_purchase(self):
        payload = {'event_type': 'add_to_cart', 'session_id': 's1', 'promotion_id': self.promo.id, 'event_id': str(uuid4())}
        for _ in range(2):
            self.assertEqual(self.client.post('/api/vivadent/public/events/', payload, format='json').status_code, 201)
        self.assertEqual(AnalyticsEvent.objects.count(), 1)
        payload['event_type'] = 'purchase'
        self.assertEqual(self.client.post('/api/vivadent/public/events/', payload, format='json').status_code, 400)

    @patch('vivadent.commerce.payment_metrics', return_value={'available': True, 'orders': 2, 'revenue': 60000, 'products': [], 'session_ids': ['s1', 'unknown']})
    def test_live_counts_and_funnel_do_not_count_tabs_or_expired_sessions(self, _):
        now = timezone.now()
        for sid in ['s1', 's2']:
            response = self.client.post('/api/vivadent/public/heartbeat/', {'session_id': sid, 'visitor_id': 'one-browser', 'cart_ids': [self.promo.id], 'active': True}, format='json')
            self.assertEqual(response.status_code, 204)
        StoreSession.objects.create(session_id='expired', visitor_id='other', last_seen=now-timedelta(seconds=61), cart_ids=[self.promo.id])
        for event in ['page_view', 'add_to_cart', 'checkout_started']:
            AnalyticsEvent.objects.create(event_type=event, session_id='s1', promotion_id=self.promo.id)
        self.assertIn(self.client.get('/api/vivadent/analytics/live/').status_code, [401, 403])
        self.admin()
        data = self.client.get('/api/vivadent/analytics/live/').data
        self.assertEqual((data['online'], data['active_carts'], data['additions']), (1, 1, 1))
        self.assertEqual(data['funnel']['purchases'], 1)
        self.assertEqual(data['conversion_rate'], 100)
        self.assertNotIn('session_ids', data['payments'])
        self.assertNotIn('visitor_id', str(data))

    def test_heartbeat_rejects_oversized_cart(self):
        self.assertEqual(self.client.post('/api/vivadent/public/heartbeat/', {'session_id': 's', 'visitor_id': 'v', 'cart_ids': list(range(1, 12)), 'active': True}, format='json').status_code, 400)

    @patch('vivadent.commerce.payment_metrics', return_value={'available': False, 'reason': 'Sin conexión'})
    def test_missing_payment_connection_is_not_reported_as_zero_sales(self, _):
        self.admin()
        data = self.client.get('/api/vivadent/analytics/live/?days=oops').data
        self.assertFalse(data['payments']['available'])
        self.assertIsNone(data['funnel']['purchases'])
        self.assertIsNone(data['conversion_rate'])

    def test_payment_bridge_uses_private_key_and_handles_unavailable_service(self):
        import io
        import json
        from django.test import override_settings
        from urllib.error import URLError
        from .commerce import payment_metrics
        payload = {'orders': 2, 'revenue': 60000, 'products': [], 'session_ids': ['s1'], 'generated_at': timezone.now().isoformat()}
        with override_settings(VIVADENT_PAYMENTS_ANALYTICS_URL='https://payments.example.test/api/v1/internal/commerce-analytics', VIVADENT_PAYMENTS_ANALYTICS_KEY='k' * 40):
            with patch('vivadent.commerce.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())) as send:
                result = payment_metrics(7)
                self.assertTrue(result['available'])
                self.assertEqual(result['orders'], 2)
                request = send.call_args.args[0]
                self.assertEqual(request.get_header('X-internal-key'), 'k' * 40)
                self.assertTrue(request.full_url.endswith('?days=7'))
            cache.clear()
            with patch('vivadent.commerce.urlopen', side_effect=URLError('offline')):
                self.assertFalse(payment_metrics(7)['available'])

    def test_hidden_tab_no_longer_counts_as_online(self):
        payload = {'session_id': 'visible', 'visitor_id': 'v1', 'cart_ids': [self.promo.id], 'active': True}
        self.client.post('/api/vivadent/public/heartbeat/', payload, format='json')
        self.client.post('/api/vivadent/public/heartbeat/', {**payload, 'active': False}, format='json')
        self.admin()
        with patch('vivadent.commerce.payment_metrics', return_value={'available': False}):
            result = self.client.get('/api/vivadent/analytics/live/').data
        self.assertEqual(result['online'], 0)
        self.assertEqual(result['active_carts'], 0)


class TreatmentSectionsTests(APITestCase):
    setUp = CommerceTests.setUp
    admin = CommerceTests.admin

    def test_four_sections_exist_in_display_order(self):
        self.assertEqual(list(StoreCollection.objects.exclude(key='packs').values_list('key', flat=True)), ['tienda', 'dental', 'facial', 'radiologia'])

    def test_create_edit_and_remove_membership(self):
        self.admin()
        response = self.client.post('/api/vivadent/promotions/', {'title': 'Pack sonrisa', 'subtitle': 'Test', 'price': '$40.000', 'description': 'Test', 'status': 'active', 'section_keys': ['tienda', 'dental']}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data['id']
        self.assertEqual(response.data['section_keys'], ['tienda', 'dental'])
        self.assertIn(pk, StoreCollection.objects.get(key='dental').promotion_ids)
        response = self.client.patch(f'/api/vivadent/promotions/{pk}/', {'section_keys': ['radiologia']}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['section_keys'], ['radiologia'])
        self.assertNotIn(pk, StoreCollection.objects.get(key='dental').promotion_ids)
        response = self.client.patch(f'/api/vivadent/promotions/{pk}/', {'price': '$45.000'}, format='json')
        self.assertEqual(response.data['section_keys'], ['radiologia'])
        self.assertEqual(self.client.patch(f'/api/vivadent/promotions/{pk}/', {'section_keys': ['unknown']}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'/api/vivadent/promotions/{pk}/', {'section_keys': ['dental', 'dental']}, format='json').status_code, 400)
        self.assertEqual(self.client.delete(f'/api/vivadent/promotions/{pk}/').status_code, 204)
        public = self.client.get('/api/vivadent/public/content/').data
        self.assertTrue(all(pk not in row['promotion_ids'] for row in public['collections']))

    def test_empty_memberships_preserve_catalog_product(self):
        self.admin()
        response = self.client.patch(f'/api/vivadent/promotions/{self.promo.id}/', {'section_keys': []}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['section_keys'], [])
        self.assertIn(self.promo.id, [p['id'] for p in self.client.get('/api/vivadent/public/content/').data['promotions']])

    def test_catalog_survives_missing_collections_table_during_deploy(self):
        from django.db import OperationalError
        with patch('vivadent.views.StoreCollection.objects.all', side_effect=OperationalError('no such table: vivadent_storecollection')):
            response = self.client.get('/api/vivadent/public/content/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['collections'])
        self.assertIn(self.promo.id, [p['id'] for p in response.data['promotions']])
        self.assertNotIn(self.draft.id, [p['id'] for p in response.data['promotions']])
        self.assertTrue(all(p['section_keys'] == [] for p in response.data['promotions']))

    def test_catalog_does_not_mask_other_database_errors(self):
        from django.db import OperationalError
        with patch('vivadent.views.StoreCollection.objects.all', side_effect=OperationalError('database is unavailable')):
            with self.assertRaises(OperationalError):
                self.client.get('/api/vivadent/public/content/')
