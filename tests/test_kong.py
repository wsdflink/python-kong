# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
from abc import ABCMeta, abstractmethod
import os
import sys
import collections
import requests
import uuid
import json
import random

# To run the standalone test script
if __name__ == '__main__':
    sys.path.append('../src/')

from kong.exceptions import ConflictError
from kong.simulator import KongAdminSimulator
from kong.client import KongAdminClient
from kong.compat import TestCase, skipIf, run_unittests, OrderedDict, urlencode
from kong.utils import uuid_or_string, add_url_params, sorted_ordered_dict

from faker import Factory
from faker.providers import BaseProvider

API_URL = os.environ.get('PYKONG_TEST_API_URL', 'http://localhost:8001')


def kong_testserver_is_up():
    try:
        return requests.get(API_URL).status_code == 200
    except IOError:
        return False

# Initialize fake
fake = Factory.create()


# Custom fake provider
class CustomInfoProvider(BaseProvider):
    def api_name(self):
        return fake.name().replace(' ', '')

    def api_path(self):
        path = fake.uri_path()
        if not path.startswith('/'):
            path = '/%s' % path
        return path

    def username(self):
        return fake.first_name().lower().replace(' ', '')

    def oauth2_app_name(self):
        return fake.sentence(nb_words=random.randint(1, 3), variable_nb_words=True).rstrip('.')

fake.add_provider(CustomInfoProvider)


class KongAdminTesting(object):
    """
    Important: Do not remove nesting!
    """
    class ClientFactoryMixin(object):
        __metaclass__ = ABCMeta

        @abstractmethod
        def on_create_client(self):
            pass

    class APITestCase(ClientFactoryMixin, TestCase):
        __metaclass__ = ABCMeta

        def setUp(self):
            self.client = self.on_create_client()
            self.assertTrue(self.client.apis.count() == 0)
            self._cleanup = []
            fake.seed(random.randint(1000, 10000000))

        def tearDown(self):
            for name_or_id in set(self._cleanup):
                self.client.apis.delete(name_or_id)
            self.assertEqual(self.client.apis.count(), 0)

        def test_add(self):
            url = fake.url()
            name = fake.api_name()
            dns = fake.domain_name()

            result = self.client.apis.add(upstream_url=url, name=name, inbound_dns=dns)
            self._cleanup_afterwards(result['id'])

            self.assertEqual(self.client.apis.count(), 1)
            self.assertEqual(result['upstream_url'], url)
            self.assertEqual(result['name'], name)
            self.assertEqual(result['inbound_dns'], dns)
            self.assertIsNotNone(result['id'])
            self.assertIsNotNone(result['created_at'])
            self.assertFalse('path' in result)

        def test_add_extra(self):
            url = fake.url()
            name = fake.api_name()
            dns = fake.domain_name()

            result = self.client.apis.add(
                upstream_url=url, name=name, inbound_dns=dns, strip_path=True)
            self._cleanup_afterwards(result['id'])

            self.assertEqual(self.client.apis.count(), 1)
            self.assertEqual(result['upstream_url'], url)
            self.assertEqual(result['name'], name)
            self.assertEqual(result['inbound_dns'], dns)
            self.assertTrue(result['strip_path'])
            self.assertIsNotNone(result['id'])
            self.assertIsNotNone(result['created_at'])
            self.assertFalse('path' in result)

        def test_add_conflict_name(self):
            url = fake.url()
            name = fake.api_name()
            dns = fake.domain_name()

            result = self.client.apis.add(upstream_url=url, name=name, inbound_dns=dns)
            self._cleanup_afterwards(result['id'])

            self.assertEqual(self.client.apis.count(), 1)

            result2 = None
            error_thrown = False
            try:
                result2 = self.client.apis.add(upstream_url=fake.url(), name=name, inbound_dns=fake.domain_name())
            except ConflictError:
                error_thrown = True
            self.assertTrue(error_thrown)
            self.assertIsNone(result2)

            self.assertEqual(self.client.apis.count(), 1)

        def test_add_conflict_public_dns(self):
            url = fake.url()
            name = fake.api_name()
            dns = fake.domain_name()

            result = self.client.apis.add(upstream_url=url, name=name, inbound_dns=dns)
            self._cleanup_afterwards(result['id'])

            self.assertEqual(self.client.apis.count(), 1)

            result2 = None
            error_thrown = False
            try:
                result2 = self.client.apis.add(upstream_url=fake.url(), name=fake.api_name(), inbound_dns=dns)
            except ConflictError:
                error_thrown = True
            self.assertTrue(error_thrown)
            self.assertIsNone(result2)

            self.assertEqual(self.client.apis.count(), 1)

        def test_add_missing_public_dns_and_path(self):
            result = None
            with self.assertRaises(ValueError):
                result = self.client.apis.add(upstream_url=fake.url())
            self.assertIsNone(result)
            self.assertEqual(self.client.apis.count(), 0)

        def test_add_missing_public_dns(self):
            result = self.client.apis.add(upstream_url=fake.url(), path=fake.api_path())
            self.assertIsNotNone(result)
            self._cleanup_afterwards(result['id']),
            self.assertEqual(self.client.apis.count(), 1)

        def test_add_missing_path(self):
            result = self.client.apis.add(upstream_url=fake.url(), inbound_dns=fake.domain_name())
            self.assertIsNotNone(result)
            self._cleanup_afterwards(result['id']),
            self.assertEqual(self.client.apis.count(), 1)

        def test_update(self):
            url = fake.url()
            name = fake.api_name()
            dns = fake.domain_name()

            result = self.client.apis.add(upstream_url=url, name=name, inbound_dns=dns)
            self._cleanup_afterwards(result['id']),

            # Update by name
            new_path = fake.api_path()
            result2 = self.client.apis.update(name, url, path=new_path, strip_path=True)
            self.assertEqual(result2['id'], result['id'])
            self.assertEqual(result2['path'], new_path)
            self.assertEqual(result2['inbound_dns'], dns)
            self.assertTrue(result2['strip_path'])

            # Update by id
            new_path = fake.api_path()
            new_url = fake.url()
            new_dns = fake.domain_name()
            result3 = self.client.apis.update(result['id'], new_url, path=new_path, inbound_dns=new_dns)
            self.assertEqual(result3['id'], result['id'])
            self.assertEqual(result3['upstream_url'], new_url)
            self.assertEqual(result3['path'], new_path)
            self.assertEqual(result3['inbound_dns'], new_dns)
            self.assertTrue(result3['strip_path'])

            # retrieve to check
            result4 = self.client.apis.retrieve(result['id'])
            self.assertIsNotNone(result4)
            self.assertEqual(result4['id'], result['id'])
            self.assertEqual(result4['upstream_url'], new_url)
            self.assertEqual(result4['path'], new_path)
            self.assertEqual(result4['inbound_dns'], new_dns)
            self.assertTrue(result4['strip_path'])

        def test_add_or_update(self):
            result = self.client.apis.add(upstream_url=fake.url(), name=fake.api_name(), inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result['id'])
            self.assertEqual(self.client.apis.count(), 1)

            # Test add_or_update without api_id -> Should ADD
            result2 = self.client.apis.add_or_update(
                upstream_url=fake.url(), name=fake.api_name(), inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result2['id'])
            self.assertEqual(self.client.apis.count(), 2)

            # Test add_or_update with api_id -> Should UPDATE
            result3 = self.client.apis.add_or_update(
                upstream_url=fake.url(), api_id=result['id'], name=fake.api_name(), inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result3['id'])
            self.assertEqual(self.client.apis.count(), 2)
            self.assertEqual(result3['id'], result['id'])

        def test_retrieve(self):
            url = fake.url()
            name = fake.api_name()
            dns = fake.domain_name()

            result = self.client.apis.add(upstream_url=url, name=name, inbound_dns=dns)
            self._cleanup_afterwards(result['id'])

            self.assertEqual(result['upstream_url'], url)
            self.assertEqual(result['name'], name)
            self.assertEqual(result['inbound_dns'], dns)

            # Retrieve by name
            result2 = self.client.apis.retrieve(name)
            self.assertEqual(result2, result)

            # Retrieve by id
            result3 = self.client.apis.retrieve(result['id'])
            self.assertEqual(result3, result)
            self.assertEqual(result3, result2)

        def test_list(self):
            amount = 5

            dns_list = [fake.domain_name() for i in range(amount)]
            for i in range(amount):
                result = self.client.apis.add(upstream_url=fake.url(), name=fake.api_name(), inbound_dns=dns_list[i])
                self._cleanup_afterwards(result['id'])

            self.assertEqual(self.client.apis.count(), amount)

            result = self.client.apis.list()
            self.assertTrue('data' in result)
            data = result['data']

            self.assertEqual(len(data), amount)

            result = self.client.apis.list(inbound_dns=dns_list[4])
            self.assertTrue('data' in result)
            data = result['data']

            self.assertEqual(len(data), 1)

            result = self.client.apis.list(size=3)
            self.assertIsNotNone(result['next'])
            self.assertEqual(len(result['data']), 3)

        def test_iterate(self):
            amount = 5

            for i in range(amount):
                result = self.client.apis.add(
                    upstream_url=fake.url(), name=fake.api_name(), inbound_dns=fake.domain_name())
                self._cleanup_afterwards(result['id'])

            found = []

            for item in self.client.apis.iterate(window_size=3):
                found.append(item)

            self.assertEqual(len(found), amount)
            self.assertEqual(
                sorted([item['id'] for item in found]),
                sorted([item['id'] for item in self.client.apis.list().get('data')]))

        def test_iterate_filtered(self):
            amount = 5

            api_names = [fake.api_name() for i in range(amount)]
            for i in range(amount):
                result = self.client.apis.add(upstream_url=fake.url(), name=api_names[i], inbound_dns=fake.domain_name())
                self._cleanup_afterwards(result['id'])

            found = []

            for item in self.client.apis.iterate(window_size=3, name=api_names[4]):
                found.append(item)

            self.assertEqual(len(found), 1)
            self.assertEqual(
                sorted([item['id'] for item in found]),
                sorted([item['id'] for item in self.client.apis.list(name=api_names[4]).get('data')]))

        def test_delete(self):
            url1 = fake.url()
            url2 = fake.url()

            result1 = self.client.apis.add(upstream_url=url1, name=fake.api_name(), inbound_dns=fake.domain_name())
            self.assertEqual(result1['upstream_url'], url1)

            result2 = self.client.apis.add(upstream_url=url2, name=fake.api_name(), inbound_dns=fake.domain_name())
            self.assertEqual(result2['upstream_url'], url2)

            self.assertEqual(self.client.apis.count(), 2)

            # Delete by id
            self.client.apis.delete(result1['id'])
            self.assertEqual(self.client.apis.count(), 1)

            # Delete by name
            self.client.apis.delete(result2['name'])
            self.assertEqual(self.client.apis.count(), 0)

        def test_create_global_plugin_configuration(self):
            api_name = fake.api_name()

            # Create test api
            result = self.client.apis.add(
                upstream_url=fake.url(), name=api_name, inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 0)

            # Create global plugin configuration for the api
            result2 = self.client.apis.plugins(api_name).create('rate-limiting', enabled=False, second=20)
            self.assertIsNotNone(result2)
            self.assertIsNotNone(result2['id'])
            self.assertIsNotNone(result2['api_id'])
            self.assertFalse(result2['enabled'])
            self.assertEqual(result2['config']['second'], 20)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 1)

        def test_create_plugin_configuration_conflict(self):
            api_name = fake.api_name()

            # Create test api
            result = self.client.apis.add(
                upstream_url=fake.url(), name=api_name, inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 0)

            # Create global plugin configuration for the api
            result2 = self.client.apis.plugins(api_name).create('rate-limiting', enabled=False, second=20)
            self.assertIsNotNone(result2)
            self.assertIsNotNone(result2['id'])

            result3 = None
            error_thrown = False
            try:
                result3 = self.client.apis.plugins(api_name).create('rate-limiting', enabled=False, second=35)
            except ConflictError as e:
                error_thrown = True
            self.assertTrue(error_thrown)
            self.assertIsNone(result3)

        def test_create_non_existing_plugin_configuration(self):
            api_name = fake.api_name()

            # Create test api
            result = self.client.apis.add(
                upstream_url=fake.url(), name=api_name, inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 0)

            result2 = None
            error_thrown = False
            try:
                result2 = self.client.apis.plugins(api_name).create('unknown_plugin', second=20)
            except ValueError:
                error_thrown = True
            self.assertTrue(error_thrown)
            self.assertIsNone(result2)

        def test_create_incorrect_plugin_configuration(self):
            api_name = fake.api_name()

            # Create test api
            result = self.client.apis.add(
                upstream_url=fake.url(), name=api_name, inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 0)

            result2 = None
            error_thrown = False
            try:
                result2 = self.client.apis.plugins(api_name).create('rate-limiting', unknown_parameter=20)
            except ValueError:
                error_thrown = True
            self.assertTrue(error_thrown)
            self.assertIsNone(result2)

        def test_create_consumer_specific_plugin_configuration(self):
            api_name = fake.api_name()

            # Create test api
            result = self.client.apis.add(
                upstream_url=fake.url(), name=api_name, inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 0)

            # Create test consumer
            consumer = self.client.consumers.create(username='abc1234')

            try:
                # Create consumer specific plugin configuration for the api
                result2 = self.client.apis.plugins(api_name).create(
                    'request-size-limiting', consumer_id=consumer['id'], allowed_payload_size=512)
                self.assertIsNotNone(result2)
                self.assertIsNotNone(result2['consumer_id'])
                self.assertEqual(result2['consumer_id'], consumer['id'])
                self.assertEqual(self.client.apis.plugins(api_name).count(), 1)
            finally:
                # Delete the test consumer
                self.client.consumers.delete(consumer['id'])

        def test_update_global_plugin_configuration(self):
            api_name = fake.api_name()

            # Create test api
            result = self.client.apis.add(
                upstream_url=fake.url(), name=api_name, inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 0)

            # Create global plugin configuration for the api
            result2 = self.client.apis.plugins(api_name).create('rate-limiting', enabled=False, second=20)
            self.assertIsNotNone(result2)
            self.assertEqual(result2['enabled'], False)
            self.assertEqual(result2['config']['second'], 20)

            # Update
            result3 = self.client.apis.plugins(api_name).update(result2['id'], enabled=True, second=27)
            self.assertIsNotNone(result3)
            self.assertEqual(result3['enabled'], True)
            self.assertEqual(result3['config']['second'], 27)

            # Make sure we still have only 1 configuration
            self.assertEqual(self.client.apis.plugins(api_name).count(), 1)

        def test_create_or_update_global_plugin_configuration(self):
            api_name = fake.api_name()

            # Create test api
            result = self.client.apis.add(
                upstream_url=fake.url(), name=api_name, inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 0)

            # Create global plugin configuration for the api
            result2 = self.client.apis.plugins(api_name).create('rate-limiting', enabled=False, second=20)
            self.assertIsNotNone(result2)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 1)

            # Test create_or_update without plugin_id -> Should CREATE
            result3 = self.client.apis.plugins(api_name).create_or_update(
                'request-size-limiting', enabled=True, allowed_payload_size=128)
            self.assertIsNotNone(result3)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 2)

            # Test create_or_update with plugin_configuration_id -> Should UPDATE
            result4 = self.client.apis.plugins(api_name).create_or_update(
                'request-size-limiting', plugin_configuration_id=result3['id'], allowed_payload_size=512)
            self.assertIsNotNone(result4)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 2)

        def test_update_incorrect_plugin_configuration(self):
            api_name = fake.api_name()

            # Create test api
            result = self.client.apis.add(
                upstream_url=fake.url(), name=api_name, inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 0)

            # Create global plugin configuration for the api
            result2 = self.client.apis.plugins(api_name).create('rate-limiting', enabled=False, second=20)
            self.assertIsNotNone(result2)
            self.assertEqual(result2['enabled'], False)
            self.assertEqual(result2['config']['second'], 20)

            # Update
            result3 = None
            error_thrown = False
            try:
                result3 = self.client.apis.plugins(api_name).update(
                    result2['name'], enabled=True, unknown_parameter=27)
            except ValueError:
                error_thrown = True
            self.assertTrue(error_thrown)
            self.assertIsNone(result3)

            # Make sure we still have only 1 configuration
            self.assertEqual(self.client.apis.plugins(api_name).count(), 1)

        def test_update_consumer_specific_plugin_configuration(self):
            api_name = fake.api_name()

            # Create test api
            result = self.client.apis.add(
                upstream_url=fake.url(), name=api_name, inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 0)

            # Create test consumer
            consumer = self.client.consumers.create(username='abc1234')

            try:
                # Create consumer specific plugin configuration for the api
                result2 = self.client.apis.plugins(api_name).create(
                    'request-size-limiting', consumer_id=consumer['id'], allowed_payload_size=512)
                self.assertIsNotNone(result2)
                self.assertIsNotNone(result2['consumer_id'])
                self.assertEqual(result2['consumer_id'], consumer['id'])
                self.assertEqual(self.client.apis.plugins(api_name).count(), 1)

                # Update
                result3 = self.client.apis.plugins(api_name).update(
                    result2['id'], consumer_id=consumer['id'], allowed_payload_size=1024)
                self.assertIsNotNone(result3)
                self.assertEqual(result3['enabled'], True)
                self.assertEqual(result3['config']['allowed_payload_size'], 1024)
                self.assertIsNotNone(result3['consumer_id'])
                self.assertEqual(result3['consumer_id'], consumer['id'])

                # Make sure we still have only 1 configuration
                self.assertEqual(self.client.apis.plugins(api_name).count(), 1)
            finally:
                # Delete the test consumer
                self.client.consumers.delete(consumer['id'])

        def test_delete_plugin_configuration(self):
            api_name = fake.api_name()

            result = self.client.apis.add(
                upstream_url=fake.url(), name=api_name, inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 0)

            result2 = self.client.apis.plugins(api_name).create('request-size-limiting', allowed_payload_size=512)
            self.assertIsNotNone(result2)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 1)

            # delete by id
            self.client.apis.plugins(api_name).delete(result2['id'])
            self.assertEqual(self.client.apis.plugins(api_name).count(), 0)

        def test_list_plugin_configuration(self):
            api_name = fake.api_name()

            result = self.client.apis.add(
                upstream_url=fake.url(), name=api_name, inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 0)

            result2 = self.client.apis.plugins(api_name).create('rate-limiting', enabled=False, second=20)
            self.assertIsNotNone(result2)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 1)

            result3 = self.client.apis.plugins(api_name).create('request-size-limiting', allowed_payload_size=512)
            self.assertIsNotNone(result3)
            self.assertEqual(self.client.apis.plugins(api_name).count(), 2)

            result4 = self.client.apis.plugins(api_name).list()
            data = result4['data']

            self.assertEqual(len(data), 2)

            result5 = self.client.apis.plugins(api_name).list(name='request-size-limiting')
            data = result5['data']

            self.assertEqual(len(data), 1)

        def test_retrieve_plugin_configuration(self):
            result = self.client.apis.add(upstream_url=fake.url(), name=fake.api_name(), inbound_dns=fake.domain_name())
            self._cleanup_afterwards(result['id'])

            api_id = result['id']

            self.assertIsNotNone(result)
            self.assertEqual(self.client.apis.plugins(api_id).count(), 0)

            result2 = self.client.apis.plugins(api_id).create('rate-limiting', enabled=False, second=20)
            self.assertIsNotNone(result2)
            self.assertEqual(self.client.apis.plugins(api_id).count(), 1)

            # Retrieve by id
            result3 = self.client.apis.plugins(api_id).retrieve(result2['id'])
            self.assertIsNotNone(result3)
            self.assertEqual(result3['api_id'], api_id)
            self.assertEqual(result3['name'], 'rate-limiting')
            self.assertFalse(result3['enabled'])
            self.assertEqual(result3['config']['second'], 20)

        def _cleanup_afterwards(self, name_or_id):
            self._cleanup.append(name_or_id)
            return name_or_id

    class ConsumerTestCase(ClientFactoryMixin, TestCase):
        __metaclass__ = ABCMeta

        def setUp(self):
            self.client = self.on_create_client()
            self.assertTrue(self.client.consumers.count() == 0)
            self._cleanup = []
            fake.seed(random.randint(1000, 10000000))

        def tearDown(self):
            for consumer_username_or_id in set(self._cleanup):
                # Cleanup basic_auth
                for basic_auth_struct in self.client.consumers.basic_auth(consumer_username_or_id).iterate():
                    self.client.consumers.basic_auth(consumer_username_or_id).delete(basic_auth_struct['id'])

                # Cleanup key auth
                for key_auth_struct in self.client.consumers.key_auth(consumer_username_or_id).iterate():
                    self.client.consumers.key_auth(consumer_username_or_id).delete(key_auth_struct['id'])

                # Cleanup oauth2
                for oauth2_struct in self.client.consumers.oauth2(consumer_username_or_id).iterate():
                    self.client.consumers.oauth2(consumer_username_or_id).delete(oauth2_struct['id'])

                # Cleanup consumer
                self.client.consumers.delete(consumer_username_or_id)
            self.assertEqual(self.client.consumers.count(), 0)

        def test_create(self):
            username = fake.username()
            custom_id = fake.uuid4()

            result = self.client.consumers.create(
                username=username, custom_id=custom_id)
            self._cleanup_afterwards(result['id'])

            self.assertIsNotNone(result)
            self.assertEqual(result['username'], username)
            self.assertEqual(result['custom_id'], custom_id)

        def test_create_or_update(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertEqual(self.client.consumers.count(), 1)

            # Test add_or_update without consumer_id -> Should CREATE
            result2 = self.client.consumers.create_or_update(
                username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result2['id'])
            self.assertEqual(self.client.consumers.count(), 2)

            # Test add_or_update with consumer_id -> Should UPDATE
            result3 = self.client.consumers.create_or_update(
                consumer_id=result['id'], username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result3['id'])
            self.assertEqual(self.client.consumers.count(), 2)
            self.assertEqual(result3['id'], result['id'])

        def test_create_only_username(self):
            username = fake.username()

            result = self.client.consumers.create(username=username)
            self._cleanup_afterwards(result['id'])
            self.assertFalse('custom_id' in result)
            self.assertEqual(result['username'], username)

        def test_create_only_custom_id(self):
            custom_id = fake.uuid4()

            result = self.client.consumers.create(custom_id=custom_id)
            self._cleanup_afterwards(result['id'])  # We have no username, so we can only delete afterwards with id
            self.assertFalse('username' in result)
            self.assertEqual(result['custom_id'], custom_id)

        def test_create_conflict(self):
            username = fake.username()
            custom_id = fake.uuid4()

            result = self.client.consumers.create(username=username, custom_id=custom_id)
            self._cleanup_afterwards(result['id'])

            result2 = None
            error_thrown = False
            try:
                result2 = self.client.consumers.create(username=username, custom_id=custom_id)
            except ConflictError:
                error_thrown = True
            self.assertTrue(error_thrown)
            self.assertIsNone(result2)

        def test_create_conflict_only_username(self):
            username = fake.username()

            result = self.client.consumers.create(username=username)
            self._cleanup_afterwards(result['id'])

            result2 = None
            error_thrown = False
            try:
                result2 = self.client.consumers.create(username=username)
            except ConflictError:
                error_thrown = True
            self.assertTrue(error_thrown)
            self.assertIsNone(result2)

        def test_create_conflict_only_custom_id(self):
            custom_id = fake.uuid4()

            result = self.client.consumers.create(custom_id=custom_id)
            self._cleanup_afterwards(result['id'])  # We have no username, so we can only delete afterwards with id

            result2 = None
            error_thrown = False
            try:
                result2 = self.client.consumers.create(custom_id=custom_id)
            except ConflictError:
                error_thrown = True
            self.assertTrue(error_thrown)
            self.assertIsNone(result2)

        def test_update(self):
            username = fake.username()
            custom_id = fake.uuid4()

            result1 = self.client.consumers.create(username=username, custom_id=custom_id)
            self.assertIsNotNone(result1)
            self._cleanup_afterwards(result1['id'])

            username = fake.username()

            # update by username
            result2 = self.client.consumers.update(result1['username'], username=username)
            self.assertIsNotNone(result2)
            self.assertEqual(result2['id'], result1['id'])
            self.assertEqual(result2['username'], username)

            username = fake.username()
            custom_id = fake.uuid4()

            # update by id
            result3 = self.client.consumers.update(result1['id'], username=username, custom_id=custom_id)
            self.assertIsNotNone(result3)
            self.assertEqual(result3['id'], result1['id'])
            self.assertEqual(result3['username'], username)
            self.assertEqual(result3['custom_id'], custom_id)

            # retrieve to check
            result4 = self.client.consumers.retrieve(result1['id'])
            self.assertIsNotNone(result4)
            self.assertEqual(result4['username'], username)
            self.assertEqual(result4['custom_id'], custom_id)

        def test_retrieve(self):
            username = fake.username()
            custom_id = fake.uuid4()

            result = self.client.consumers.create(username=username, custom_id=custom_id)
            self._cleanup_afterwards(result['id'])
            self.assertEqual(result['username'], username)
            self.assertEqual(result['custom_id'], custom_id)

            # Retrieve by username
            result2 = self.client.consumers.retrieve(username)
            self.assertEqual(result2, result)

            # Retrieve by id
            result3 = self.client.consumers.retrieve(result['id'])
            self.assertEqual(result3, result)
            self.assertEqual(result3, result2)

        def test_list(self):
            amount = 5

            usernames = [fake.username() for i in range(amount)]
            custom_ids = [fake.uuid4() for i in range(amount)]

            for i in range(amount):
                result = self.client.consumers.create(username=usernames[i], custom_id=custom_ids[i])
                self._cleanup_afterwards(result['id'])

            self.assertEqual(self.client.consumers.count(), amount)

            result = self.client.consumers.list()
            self.assertTrue('data' in result)
            data = result['data']

            self.assertEqual(len(data), amount)

            result = self.client.consumers.list(custom_id=custom_ids[4])
            self.assertTrue('data' in result)
            data = result['data']

            self.assertEqual(len(data), 1)

            result = self.client.consumers.list(size=3)
            self.assertIsNotNone(result['next'])
            self.assertEqual(len(result['data']), 3)

        def test_iterate(self):
            amount = 5

            usernames = [fake.username() for i in range(amount)]
            custom_ids = [fake.uuid4() for i in range(amount)]

            for i in range(amount):
                result = self.client.consumers.create(username=usernames[i], custom_id=custom_ids[i])
                self._cleanup_afterwards(result['id'])

            found = []

            for item in self.client.consumers.iterate(window_size=3):
                found.append(item)

            self.assertEqual(len(found), amount)
            self.assertEqual(
                sorted([item['id'] for item in found]),
                sorted([item['id'] for item in self.client.consumers.list().get('data')]))

        def test_delete(self):
            usernames = [fake.username() for i in range(2)]
            custom_ids = [fake.uuid4() for i in range(2)]

            result1 = self.client.consumers.create(username=usernames[0], custom_id=custom_ids[0])
            self.assertEqual(result1['username'], usernames[0])
            result2 = self.client.consumers.create(username=usernames[1], custom_id=custom_ids[1])
            self.assertEqual(result2['username'], usernames[1])

            self.assertEqual(self.client.consumers.count(), 2)

            # Delete by id
            self.client.consumers.delete(result1['id'])
            self.assertEqual(self.client.consumers.count(), 1)

            # Delete by username
            self.client.consumers.delete(result2['username'])
            self.assertEqual(self.client.consumers.count(), 0)

        def test_basic_auth_create(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            test_username = fake.username()
            test_password = fake.password()

            result2 = self.client.consumers.basic_auth(result['id']).create(
                username=test_username, password=test_password)
            self.assertIsNotNone(result2)
            self.assertTrue('id' in result2)
            self.assertEqual(result2['username'], test_username)
            self.assertEqual(result2['password'], test_password)

        def test_basic_auth_update(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            test_username = fake.username()
            test_password = fake.password()

            # Create
            result2 = self.client.consumers.basic_auth(result['id']).create(
                username=test_username, password=test_password)
            self.assertIsNotNone(result2)

            test_username = fake.username()
            test_password = fake.password()

            # Update
            result3 = self.client.consumers.basic_auth(result['id']).update(
                result2['id'], username=test_username, password=test_password)
            self.assertIsNotNone(result3)
            self.assertEqual(result3['username'], test_username)
            self.assertEqual(result3['password'], test_password)

            # Retrieve and verify
            result4 = self.client.consumers.basic_auth(result['id']).retrieve(result2['id'])
            self.assertIsNotNone(result4)
            self.assertEqual(result4['username'], result3['username'])
            self.assertEqual(result4['password'], result3['password'])

        def test_basic_auth_create_or_update(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            result2 = self.client.consumers.basic_auth(result['id']).create(
                username=fake.username(), password=fake.password())
            self.assertIsNotNone(result2)

            test_username = fake.username()
            test_password = fake.password()

            # Test create_or_update without basic_auth_id -> Should CREATE
            result3 = self.client.consumers.basic_auth(result['id']).create_or_update(
                username=test_username, password=test_password)
            self.assertIsNotNone(result3)
            self.assertNotEqual(result3['id'], result2['id'])
            self.assertEqual(result3['username'], test_username)
            self.assertEqual(result3['password'], test_password)
            self.assertEqual(self.client.consumers.basic_auth(result['id']).count(), 2)

            test_username = fake.username()
            test_password = fake.password()

            # Test create_or_update with basic_auth_id -> Should UPDATE
            result4 = self.client.consumers.basic_auth(result['id']).create_or_update(
                basic_auth_id=result3['id'], username=test_username, password=test_password)
            self.assertIsNotNone(result4)
            self.assertEqual(result4['id'], result3['id'])
            self.assertEqual(result4['username'], test_username)
            self.assertEqual(result4['password'], test_password)
            self.assertEqual(self.client.consumers.basic_auth(result['id']).count(), 2)

        def test_basic_auth_retrieve(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            result2 = self.client.consumers.basic_auth(result['id']).create(
                username=fake.username(), password=fake.password())
            self.assertIsNotNone(result2)

            # Retrieve by id
            result3 = self.client.consumers.basic_auth(result['id']).retrieve(result2['id'])
            self.assertEqual(result3['id'], result2['id'])
            self.assertEqual(result3['username'], result2['username'])
            self.assertEqual(result3['password'], result2['password'])

        def test_basic_auth_list(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            amount = 5

            usernames = [fake.username() for i in range(amount)]
            passwords = [fake.password() for i in range(amount)]

            for i in range(amount):
                self.client.consumers.basic_auth(result['id']).create(username=usernames[i], password=passwords[i])

            self.assertEqual(self.client.consumers.basic_auth(result['id']).count(), amount)

            result2 = self.client.consumers.basic_auth(result['id']).list()
            self.assertTrue('data' in result2)
            data = result2['data']

            self.assertEqual(len(data), amount)

            result3 = self.client.consumers.basic_auth(result['id']).list(username=usernames[2])
            self.assertTrue('data' in result3)
            data = result3['data']

            self.assertEqual(len(data), 1)

            result4 = self.client.consumers.basic_auth(result['id']).list(size=3)
            self.assertIsNotNone(result4['next'])
            self.assertEqual(len(result4['data']), 3)

        def test_basic_auth_iterate(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            amount = 5

            usernames = [fake.username() for i in range(amount)]
            passwords = [fake.password() for i in range(amount)]

            for i in range(amount):
                self.client.consumers.basic_auth(result['id']).create(username=usernames[i], password=passwords[i])

            self.assertEqual(self.client.consumers.basic_auth(result['id']).count(), amount)

            found = []

            for item in self.client.consumers.basic_auth(result['id']).iterate(window_size=2):
                found.append(item)

            self.assertEqual(len(found), amount)
            self.assertEqual(
                sorted([item['id'] for item in found]),
                sorted([item['id'] for item in self.client.consumers.basic_auth(result['id']).list().get('data')]))

        def test_basic_auth_delete(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            result2 = self.client.consumers.basic_auth(result['id']).create(
                username=fake.username(), password=fake.password())
            self.assertIsNotNone(result2)
            self.assertTrue('id' in result2)
            self.assertEqual(self.client.consumers.basic_auth(result['id']).count(), 1)

            # Delete by ID
            self.client.consumers.basic_auth(result['id']).delete(result2['id'])
            self.assertEqual(self.client.consumers.basic_auth(result['id']).count(), 0)

        def test_key_auth_create(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            result2 = self.client.consumers.key_auth(result['id']).create()
            self.assertIsNotNone(result2)
            self.assertTrue('id' in result2)
            self.assertIsNotNone(result2['key'])

            test_key = fake.password(length=128)

            result3 = self.client.consumers.key_auth(result['id']).create(key=test_key)
            self.assertIsNotNone(result3)
            self.assertTrue('id' in result3)
            self.assertEqual(result3['key'], test_key)

        def test_key_auth_update(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            # Create
            result2 = self.client.consumers.key_auth(result['id']).create(key=fake.password(length=128))
            self.assertIsNotNone(result2)

            test_key = fake.password(length=128)

            # Update
            result3 = self.client.consumers.key_auth(result['id']).update(
                result2['id'], key=test_key)
            self.assertIsNotNone(result3)
            self.assertEqual(result3['key'], test_key)

            # Retrieve and verify
            result4 = self.client.consumers.key_auth(result['id']).retrieve(result2['id'])
            self.assertIsNotNone(result4)
            self.assertEqual(result4['key'], test_key)

        def test_key_auth_create_or_update(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            result2 = self.client.consumers.key_auth(result['id']).create(key=fake.password(length=128))
            self.assertIsNotNone(result2)

            test_key = fake.password(length=128)

            # Test create_or_update without key_auth_id -> Should CREATE
            result3 = self.client.consumers.key_auth(result['id']).create_or_update(key=test_key)
            self.assertIsNotNone(result3)
            self.assertNotEqual(result3['id'], result2['id'])
            self.assertEqual(result3['key'], test_key)
            self.assertEqual(self.client.consumers.key_auth(result['id']).count(), 2)

            test_key = fake.password(length=128)

            # Test create_or_update with key_auth_id -> Should UPDATE
            result4 = self.client.consumers.key_auth(result['id']).create_or_update(
                key_auth_id=result3['id'], key=test_key)
            self.assertIsNotNone(result4)
            self.assertEqual(result4['id'], result3['id'])
            self.assertEqual(result4['key'], test_key)
            self.assertEqual(self.client.consumers.key_auth(result['id']).count(), 2)

        def test_key_auth_retrieve(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            result2 = self.client.consumers.key_auth(result['id']).create(key=fake.password(length=128))
            self.assertIsNotNone(result2)

            # Retrieve by id
            result3 = self.client.consumers.key_auth(result['id']).retrieve(result2['id'])
            self.assertEqual(result3['id'], result2['id'])
            self.assertEqual(result3['key'], result2['key'])

        def test_key_auth_list(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            amount = 5

            keys = [fake.password(length=128) for i in range(amount)]

            for i in range(amount):
                self.client.consumers.key_auth(result['id']).create(key=keys[i])

            self.assertEqual(self.client.consumers.key_auth(result['id']).count(), amount)

            result2 = self.client.consumers.key_auth(result['id']).list()
            self.assertTrue('data' in result2)
            data = result2['data']

            self.assertEqual(len(data), amount)

            result3 = self.client.consumers.key_auth(result['id']).list(key=keys[3])
            self.assertTrue('data' in result3)
            data = result3['data']

            self.assertEqual(len(data), 1)

            result4 = self.client.consumers.key_auth(result['id']).list(size=3)
            self.assertIsNotNone(result4['next'])
            self.assertEqual(len(result4['data']), 3)

        def test_key_auth_iterate(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            amount = 5

            keys = [fake.password(length=128) for i in range(amount)]

            for i in range(amount):
                self.client.consumers.key_auth(result['id']).create(key=keys[i])

            self.assertEqual(self.client.consumers.key_auth(result['id']).count(), amount)

            found = []

            for item in self.client.consumers.key_auth(result['id']).iterate(window_size=2):
                found.append(item)

            self.assertEqual(len(found), amount)
            self.assertEqual(
                sorted([item['id'] for item in found]),
                sorted([item['id'] for item in self.client.consumers.key_auth(result['id']).list().get('data')]))

        def test_key_auth_delete(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            result2 = self.client.consumers.key_auth(result['id']).create(key=fake.password(length=128))
            self.assertIsNotNone(result2)
            self.assertTrue('id' in result2)
            self.assertEqual(self.client.consumers.key_auth(result['id']).count(), 1)

            # Delete by ID
            self.client.consumers.key_auth(result['id']).delete(result2['id'])
            self.assertEqual(self.client.consumers.basic_auth(result['id']).count(), 0)

        def test_oauth2_create(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            name = fake.oauth2_app_name()
            redirect_uri = fake.uri()

            result2 = self.client.consumers.oauth2(result['id']).create(name=name, redirect_uri=redirect_uri)
            self.assertIsNotNone(result2)
            self.assertTrue('id' in result2)
            self.assertEqual(result2['name'], name)
            self.assertEqual(result2['redirect_uri'], redirect_uri)

        def test_oauth2_update(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            # Create
            result2 = self.client.consumers.oauth2(result['id']).create(
                name=fake.oauth2_app_name(), redirect_uri=fake.uri())
            self.assertIsNotNone(result2)

            test_name = fake.oauth2_app_name()
            test_redirect_uri = fake.uri()

            # Update
            result3 = self.client.consumers.oauth2(result['id']).update(
                result2['id'], name=test_name, redirect_uri=test_redirect_uri)
            self.assertIsNotNone(result3)
            self.assertEqual(result3['name'], test_name)
            self.assertEqual(result3['redirect_uri'], test_redirect_uri)

            # Retrieve and verify
            result4 = self.client.consumers.oauth2(result['id']).retrieve(result2['id'])
            self.assertIsNotNone(result4)
            self.assertEqual(result4['name'], result3['name'])
            self.assertEqual(result4['redirect_uri'], result3['redirect_uri'])

        def test_oauth2_create_or_update(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            result2 = self.client.consumers.oauth2(result['id']).create(
                name=fake.oauth2_app_name(), redirect_uri=fake.uri())
            self.assertIsNotNone(result2)

            test_name = fake.oauth2_app_name()
            test_redirect_uri = fake.uri()

            # Test create_or_update without oauth2_id -> Should CREATE
            result3 = self.client.consumers.oauth2(result['id']).create_or_update(
                name=test_name, redirect_uri=test_redirect_uri)
            self.assertIsNotNone(result3)
            self.assertNotEqual(result3['id'], result2['id'])
            self.assertEqual(result3['name'], test_name)
            self.assertEqual(result3['redirect_uri'], test_redirect_uri)
            self.assertEqual(self.client.consumers.oauth2(result['id']).count(), 2)

            test_name = fake.oauth2_app_name()
            test_redirect_uri = fake.uri()

            # Test create_or_update with oauth2_id -> Should UPDATE
            result4 = self.client.consumers.oauth2(result['id']).create_or_update(
                oauth2_id=result3['id'], name=test_name, redirect_uri=test_redirect_uri)
            self.assertIsNotNone(result4)
            self.assertEqual(result4['id'], result3['id'])
            self.assertEqual(result4['name'], test_name)
            self.assertEqual(result4['redirect_uri'], test_redirect_uri)
            self.assertEqual(self.client.consumers.oauth2(result['id']).count(), 2)

        def test_oauth2_retrieve(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            result2 = self.client.consumers.oauth2(result['id']).create(
                name=fake.oauth2_app_name(), redirect_uri=fake.uri())
            self.assertIsNotNone(result2)

            # Retrieve by id
            result3 = self.client.consumers.oauth2(result['id']).retrieve(result2['id'])
            self.assertIsNotNone(result3)
            self.assertEqual(result3['name'], result2['name'])
            self.assertEqual(result3['redirect_uri'], result2['redirect_uri'])

        def test_oauth2_list(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            amount = 5

            names = [fake.oauth2_app_name() for i in range(amount)]
            redirect_uri = [fake.uri() for i in range(amount)]

            for i in range(amount):
                self.client.consumers.oauth2(result['id']).create(name=names[i], redirect_uri=redirect_uri[i])

            self.assertEqual(self.client.consumers.oauth2(result['id']).count(), amount)

            result2 = self.client.consumers.oauth2(result['id']).list()
            self.assertTrue('data' in result2)
            data = result2['data']

            self.assertEqual(len(data), amount)

            result3 = self.client.consumers.oauth2(result['id']).list(name=names[3])
            self.assertTrue('data' in result3)
            data = result3['data']

            self.assertEqual(len(data), 1)

            result4 = self.client.consumers.oauth2(result['id']).list(size=3)
            self.assertIsNotNone(result4['next'])
            self.assertEqual(len(result4['data']), 3)

        def test_oauth2_iterate(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            amount = 5

            names = [fake.oauth2_app_name() for i in range(amount)]
            redirect_uri = [fake.uri() for i in range(amount)]

            for i in range(amount):
                self.client.consumers.oauth2(result['id']).create(name=names[i], redirect_uri=redirect_uri[i])

            self.assertEqual(self.client.consumers.oauth2(result['id']).count(), amount)

            found = []

            for item in self.client.consumers.oauth2(result['id']).iterate(window_size=2):
                found.append(item)

            self.assertEqual(len(found), amount)
            self.assertEqual(
                sorted([item['id'] for item in found]),
                sorted([item['id'] for item in self.client.consumers.oauth2(result['id']).list().get('data')]))

        def test_oauth2_delete(self):
            result = self.client.consumers.create(username=fake.username(), custom_id=fake.uuid4())
            self._cleanup_afterwards(result['id'])
            self.assertIsNotNone(result)

            result2 = self.client.consumers.oauth2(result['id']).create(
                name=fake.oauth2_app_name(), redirect_uri=fake.uri())
            self.assertIsNotNone(result2)
            self.assertTrue('id' in result2)
            self.assertEqual(self.client.consumers.oauth2(result['id']).count(), 1)

            # Delete by ID
            self.client.consumers.oauth2(result['id']).delete(result2['id'])
            self.assertEqual(self.client.consumers.oauth2(result['id']).count(), 0)

        def _cleanup_afterwards(self, username_or_id):
            self._cleanup.append(username_or_id)
            return username_or_id

    class PluginTestCase(ClientFactoryMixin, TestCase):
        __metaclass__ = ABCMeta

        def setUp(self):
            self.client = self.on_create_client()
            fake.seed(random.randint(1000, 10000000))

        def test_list(self):
            result = self.client.plugins.list()
            self.assertIsNotNone(result)
            self.assertTrue('enabled_plugins' in result)
            self.assertTrue(isinstance(result['enabled_plugins'], collections.Iterable))

        def test_retrieve_schema(self):
            result = self.client.plugins.list()
            self.assertIsNotNone(result)

            # sanity check
            self.assertTrue(len(result['enabled_plugins']) >= 1)

            for plugin_name in result['enabled_plugins']:
                schema = self.client.plugins.retrieve_schema(plugin_name)
                self.assertIsNotNone(schema)
                self.assertTrue(isinstance(schema, dict))


class UtilTestCase(TestCase):
    def test_uuid_or_string_uuid(self):
        input = uuid.uuid4()
        result = uuid_or_string(input)
        self.assertEqual(result, str(input))

    def test_uuid_or_string_incorrect_value(self):
        result = None
        error_thrown = False
        try:
            result = uuid_or_string(1234)
        except ValueError:
            error_thrown = True
        self.assertTrue(error_thrown)
        self.assertIsNone(result)

    def test_add_url_params(self):
        params = OrderedDict({
            'bla1': 1,
            'bla2': 'hello',
            'bla3': True,
            'bla4': sorted_ordered_dict({'a': 1, 'b': ['a', 2, False]})
        })
        url = '%s%s' % (fake.url(), fake.uri_path())
        result = add_url_params('%s/?x=0' % url, params)
        expected_result = \
            '%s/?bla1=1&bla2=hello&bla3=%s&%s&x=0' % (
                url, json.dumps(True),
                urlencode({
                    'bla4': json.dumps(params['bla4'])
                }))
        self.assertEqual(result, expected_result)


class SimulatorAPITestCase(KongAdminTesting.APITestCase):
    def on_create_client(self):
        return KongAdminSimulator()


class SimulatorConsumerTestCase(KongAdminTesting.ConsumerTestCase):
    def on_create_client(self):
        return KongAdminSimulator()


# class SimulatorPluginTestCase(KongAdminTesting.PluginTestCase):
#     def on_create_client(self):
#         return KongAdminSimulator()


@skipIf(kong_testserver_is_up() is False, 'Kong testserver is down')
class ClientAPITestCase(KongAdminTesting.APITestCase):
    def on_create_client(self):
        return KongAdminClient(API_URL)


@skipIf(kong_testserver_is_up() is False, 'Kong testserver is down')
class ClientConsumerTestCase(KongAdminTesting.ConsumerTestCase):
    def on_create_client(self):
        return KongAdminClient(API_URL)


# @skipIf(kong_testserver_is_up() is False, 'Kong testserver is down')
# class ClientPluginTestCase(KongAdminTesting.PluginTestCase):
#     def on_create_client(self):
#         return KongAdminClient(API_URL)


if __name__ == '__main__':
    run_unittests()
