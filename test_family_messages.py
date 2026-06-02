"""
亲情留言板功能单元测试
覆盖所有4个核心API接口及权限控制逻辑
"""

import unittest
import sys
import os
import json

sys.path.insert(0, os.path.dirname(__file__))

from app import app


class FamilyMessagesTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()

    def _login_family(self):
        return self.client.post('/api/v1/auth/login', json={
            'username': 'family1', 'password': 'Family@123'
        })

    def _login_caregiver(self):
        return self.client.post('/api/v1/auth/login', json={
            'username': 'caregiver1', 'password': 'Caregiver@123'
        })

    def _login_admin(self):
        return self.client.post('/api/v1/auth/login', json={
            'username': 'admin', 'password': 'Admin@123'
        })

    def _logout(self):
        self.client.post('/api/v1/auth/logout')

    def test_01_family_send_text_message(self):
        self._login_family()
        rv = self.client.post('/api/v1/family-messages/send', json={
            'elder_id': 1, 'content': '测试亲情留言', 'message_type': 'text'
        })
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self.assertEqual(data['msg'], '留言发送成功')
        self.assertIn('id', data['data'])
        self._logout()

    def test_02_family_send_empty_content(self):
        self._login_family()
        rv = self.client.post('/api/v1/family-messages/send', json={
            'elder_id': 1, 'content': '', 'message_type': 'text'
        })
        data = rv.get_json()
        self.assertEqual(data['code'], 400)
        self._logout()

    def test_03_family_send_too_long_content(self):
        self._login_family()
        rv = self.client.post('/api/v1/family-messages/send', json={
            'elder_id': 1, 'content': 'x' * 501, 'message_type': 'text'
        })
        data = rv.get_json()
        self.assertEqual(data['code'], 400)
        self._logout()

    def test_04_family_send_to_unbound_elder(self):
        self._login_family()
        rv = self.client.post('/api/v1/family-messages/send', json={
            'elder_id': 5, 'content': 'test', 'message_type': 'text'
        })
        data = rv.get_json()
        self.assertEqual(data['code'], 403)
        self._logout()

    def test_05_family_send_without_elder_id(self):
        self._login_family()
        rv = self.client.post('/api/v1/family-messages/send', json={
            'content': 'test', 'message_type': 'text'
        })
        data = rv.get_json()
        self.assertEqual(data['code'], 400)
        self._logout()

    def test_06_caregiver_send_text_message(self):
        self._login_caregiver()
        rv = self.client.post('/api/v1/family-messages/send', json={
            'elder_id': 1, 'content': '护工回复测试', 'message_type': 'text'
        })
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self._logout()

    def test_07_caregiver_send_to_unassigned_elder(self):
        self._login_caregiver()
        rv = self.client.post('/api/v1/family-messages/send', json={
            'elder_id': 5, 'content': 'test', 'message_type': 'text'
        })
        data = rv.get_json()
        self.assertIn(data['code'], [400, 403])
        self._logout()

    def test_08_get_messages_family(self):
        self._login_family()
        rv = self.client.get('/api/v1/family-messages/list?elder_id=1&page=1&page_size=20&order=asc')
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self.assertIn('list', data['data'])
        self.assertIn('pagination', data['data'])
        self._logout()

    def test_09_get_messages_caregiver(self):
        self._login_caregiver()
        rv = self.client.get('/api/v1/family-messages/list?elder_id=1&page=1&page_size=20')
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self._logout()

    def test_10_get_messages_unauthenticated(self):
        self._logout()
        rv = self.client.get('/api/v1/family-messages/list?elder_id=1')
        data = rv.get_json()
        self.assertEqual(data['code'], 401)

    def test_11_get_messages_pagination(self):
        self._login_family()
        rv = self.client.get('/api/v1/family-messages/list?elder_id=1&page=1&page_size=5')
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self.assertEqual(data['data']['pagination']['page'], 1)
        self.assertEqual(data['data']['pagination']['page_size'], 5)
        self._logout()

    def test_12_get_messages_filter_unread(self):
        self._login_family()
        rv = self.client.get('/api/v1/family-messages/list?elder_id=1&is_read=0')
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self._logout()

    def test_13_mark_read_by_elder_id(self):
        self._login_family()
        rv = self.client.post('/api/v1/family-messages/mark-read', json={
            'elder_id': 1
        })
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self.assertEqual(data['msg'], '标记已读成功')
        self._logout()

    def test_14_mark_read_by_message_ids(self):
        self._login_family()
        rv = self.client.get('/api/v1/family-messages/list?elder_id=1&page=1&page_size=10')
        data = rv.get_json()
        if data['data']['list']:
            msg_ids = [m['id'] for m in data['data']['list'][:3]]
            rv2 = self.client.post('/api/v1/family-messages/mark-read', json={
                'message_ids': msg_ids
            })
            data2 = rv2.get_json()
            self.assertEqual(data2['code'], 200)
        self._logout()

    def test_15_mark_read_unbound_elder(self):
        self._login_family()
        rv = self.client.post('/api/v1/family-messages/mark-read', json={
            'elder_id': 5
        })
        data = rv.get_json()
        self.assertEqual(data['code'], 403)
        self._logout()

    def test_16_mark_read_no_params(self):
        self._login_family()
        rv = self.client.post('/api/v1/family-messages/mark-read', json={})
        data = rv.get_json()
        self.assertEqual(data['code'], 400)
        self._logout()

    def test_17_get_festival_templates(self):
        self._login_family()
        rv = self.client.get('/api/v1/family-messages/festival-templates')
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self.assertIsInstance(data['data'], list)
        self.assertGreater(len(data['data']), 0)
        self.assertIn('name', data['data'][0])
        self.assertIn('content', data['data'][0])
        self._logout()

    def test_18_get_festival_templates_caregiver(self):
        self._login_caregiver()
        rv = self.client.get('/api/v1/family-messages/festival-templates')
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self._logout()

    def test_19_get_unread_count(self):
        self._login_family()
        rv = self.client.get('/api/v1/family-messages/unread-count')
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self.assertIn('count', data['data'])
        self._logout()

    def test_20_get_elders_with_unread(self):
        self._login_family()
        rv = self.client.get('/api/v1/family-messages/elders-with-unread')
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self.assertIsInstance(data['data'], list)
        if len(data['data']) > 0:
            self.assertIn('id', data['data'][0])
            self.assertIn('name', data['data'][0])
            self.assertIn('unread_count', data['data'][0])
        self._logout()

    def test_21_admin_list_messages(self):
        self._login_admin()
        rv = self.client.get('/api/v1/family-messages/admin/list?page=1&page_size=10')
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self.assertIn('list', data['data'])
        self.assertIn('pagination', data['data'])
        self._logout()

    def test_22_admin_list_filter_by_elder(self):
        self._login_admin()
        rv = self.client.get('/api/v1/family-messages/admin/list?elder_id=1')
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self._logout()

    def test_23_admin_list_filter_by_sender_type(self):
        self._login_admin()
        rv = self.client.get('/api/v1/family-messages/admin/list?sender_type=family')
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        for msg in data['data']['list']:
            self.assertEqual(msg['sender_type'], 'family')
        self._logout()

    def test_24_admin_stats(self):
        self._login_admin()
        rv = self.client.get('/api/v1/family-messages/admin/stats')
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self.assertIn('total', data['data'])
        self.assertIn('family_count', data['data'])
        self.assertIn('caregiver_count', data['data'])
        self.assertIn('unread_count', data['data'])
        self.assertIn('voice_count', data['data'])
        self._logout()

    def test_25_admin_cannot_send_message(self):
        self._login_admin()
        rv = self.client.post('/api/v1/family-messages/send', json={
            'elder_id': 1, 'content': 'admin test', 'message_type': 'text'
        })
        data = rv.get_json()
        self.assertEqual(data['code'], 403)
        self._logout()

    def test_26_send_with_invalid_message_type(self):
        self._login_family()
        rv = self.client.post('/api/v1/family-messages/send', json={
            'elder_id': 1, 'content': 'test', 'message_type': 'video'
        })
        data = rv.get_json()
        self.assertEqual(data['code'], 400)
        self._logout()

    def test_27_data_isolation_from_messages_table(self):
        self._login_family()
        rv = self.client.get('/api/v1/family-messages/list?elder_id=1&page=1&page_size=100')
        data = rv.get_json()
        family_msgs = data['data']['list']
        for msg in family_msgs:
            self.assertIn('sender_type', msg, "family_messages应包含sender_type字段")
            self.assertIn('message_type', msg, "family_messages应包含message_type字段")
            self.assertIn('voice_file_path', msg, "family_messages应包含voice_file_path字段")
            self.assertNotIn('title', msg, "family_messages不应包含messages表的title字段")
        self._logout()

    def test_28_caregiver_get_elders_with_unread(self):
        self._login_caregiver()
        rv = self.client.get('/api/v1/family-messages/elders-with-unread')
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self.assertIsInstance(data['data'], list)
        self._logout()

    def test_29_admin_list_filter_by_date(self):
        self._login_admin()
        rv = self.client.get('/api/v1/family-messages/admin/list?start_date=2020-01-01&end_date=2030-12-31')
        data = rv.get_json()
        self.assertEqual(data['code'], 200)
        self._logout()

    def test_30_family_pages_accessible(self):
        self._login_family()
        rv = self.client.get('/family/family-messages')
        self.assertEqual(rv.status_code, 200)
        self._logout()

    def test_31_caregiver_pages_accessible(self):
        self._login_caregiver()
        rv = self.client.get('/caregiver/family-messages')
        self.assertEqual(rv.status_code, 200)
        self._logout()

    def test_32_admin_pages_accessible(self):
        self._login_admin()
        rv = self.client.get('/admin/family-messages')
        self.assertEqual(rv.status_code, 200)
        self._logout()


if __name__ == '__main__':
    unittest.main(verbosity=2)
