# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
from future.standard_library import hooks
import requests

with hooks():
    from urllib.parse import urljoin

from http.client import OK, CREATED, CONFLICT, NO_CONTENT

from .contract import KongAdminContract, APIAdminContract, ConsumerAdminContract, PluginAdminContract, \
    APIPluginConfigurationAdminContract
from .utils import add_url_params, assert_dict_keys_in, ensure_trailing_slash
from .exceptions import ConflictError


class RestClient(object):
    def __init__(self, api_url):
        self.api_url = api_url
        self._session = None

    @property
    def session(self):
        if self._session is None:
            self._session = requests.session()
        return self._session

    def get_url(self, *path, **query_params):
        url = ensure_trailing_slash(urljoin(self.api_url, '/'.join(path)))
        return add_url_params(url, query_params)


class APIPluginConfigurationAdminClient(APIPluginConfigurationAdminContract, RestClient):
    def __init__(self, api_admin, api_name_or_id, api_url):
        super(APIPluginConfigurationAdminClient, self).__init__(api_url)

        self.api_admin = api_admin
        self.api_name_or_id = api_name_or_id

    def create(self, plugin_name, enabled=True, consumer_id=None, **fields):
        values = {}
        for key in fields:
            values['value.%s' % key] = fields[key]

        response = self.session.post(self.get_url('apis', self.api_name_or_id, 'plugins'), data=dict({
            'name': plugin_name,
            'enabled': enabled,
            'consumer_id': consumer_id,
        }, **values))
        result = response.json()
        if response.status_code == CONFLICT:
            raise ConflictError(', '.join(result.values()))

        assert response.status_code == CREATED

        return result

    def update(self, plugin_name_or_id, enabled=True, consumer_id=None, **fields):
        return super(APIPluginConfigurationAdminClient, self).update(plugin_name_or_id, consumer_id, **fields)

    def list(self, size=100, offset=None, **filter_fields):
        assert_dict_keys_in(filter_fields, ['id', 'name', 'api_id', 'consumer_id'])

        query_params = filter_fields
        query_params['size'] = size

        if offset:
            query_params['offset'] = offset

        url = self.get_url('apis', self.api_name_or_id, 'plugins', **query_params)
        response = self.session.get(url)

        assert response.status_code == OK

        return response.json()

    def delete(self, plugin_name_or_id):
        response = self.session.delete(self.get_url('apis', self.api_name_or_id, 'plugins', plugin_name_or_id))

        assert response.status_code == NO_CONTENT

    def count(self):
        response = self.session.get(self.get_url('apis', self.api_name_or_id, 'plugins'))
        result = response.json()
        amount = result.get('total', len(result.get('data')))
        return amount


class APIAdminClient(APIAdminContract, RestClient):
    def __init__(self, api_url):
        super(APIAdminClient, self).__init__(api_url)

    def count(self):
        response = self.session.get(self.get_url('apis'))
        result = response.json()
        amount = result.get('total', len(result.get('data')))
        return amount

    def add(self, target_url, name=None, public_dns=None, path=None, strip_path=False):
        response = self.session.post(self.get_url('apis'), data={
            'name': name,
            'public_dns': public_dns,
            'path': path,
            'strip_path': strip_path,
            'target_url': target_url
        })
        result = response.json()
        if response.status_code == CONFLICT:
            raise ConflictError(', '.join(result.values()))

        assert response.status_code == CREATED

        return result

    def update(self, name_or_id, target_url, **fields):
        assert_dict_keys_in(fields, ['name', 'public_dns', 'path', 'strip_path'])
        response = self.session.patch(self.get_url('apis', name_or_id), data=dict({
            'target_url': target_url
        }, **fields))
        result = response.json()

        assert response.status_code == OK

        return result

    def delete(self, name_or_id):
        response = self.session.delete(self.get_url('apis', name_or_id))

        assert response.status_code == NO_CONTENT

    def retrieve(self, name_or_id):
        response = self.session.get(self.get_url('apis', name_or_id))

        assert response.status_code == OK

        return response.json()

    def list(self, size=100, offset=None, **filter_fields):
        assert_dict_keys_in(filter_fields, ['id', 'name', 'public_dns', 'target_url'])

        query_params = filter_fields
        query_params['size'] = size

        if offset:
            query_params['offset'] = offset

        url = self.get_url('apis', **query_params)
        response = self.session.get(url)

        assert response.status_code == OK

        return response.json()

    def plugins(self, name_or_id):
        return APIPluginConfigurationAdminClient(self, name_or_id, self.api_url)


class ConsumerAdminClient(ConsumerAdminContract, RestClient):
    def __init__(self, api_url):
        super(ConsumerAdminClient, self).__init__(api_url)

    def count(self):
        response = self.session.get(self.get_url('consumers'))
        result = response.json()
        amount = result.get('total', len(result.get('data')))
        return amount

    def create(self, username=None, custom_id=None):
        response = self.session.post(self.get_url('consumers'), data={
            'username': username,
            'custom_id': custom_id,
        })
        result = response.json()
        if response.status_code == CONFLICT:
            raise ConflictError(', '.join(result.values()))

        assert response.status_code == CREATED

        return result

    def update(self, username_or_id, **fields):
        assert_dict_keys_in(fields, ['username', 'custom_id'])
        response = self.session.patch(self.get_url('consumers', username_or_id), data=fields)
        result = response.json()

        assert response.status_code == OK

        return result

    def list(self, size=100, offset=None, **filter_fields):
        assert_dict_keys_in(filter_fields, ['id', 'custom_id', 'username'])

        query_params = filter_fields
        query_params['size'] = size

        if offset:
            query_params['offset'] = offset

        url = self.get_url('consumers', **query_params)
        response = self.session.get(url)

        assert response.status_code == OK

        return response.json()

    def delete(self, username_or_id):
        response = self.session.delete(self.get_url('consumers', username_or_id))

        assert response.status_code == NO_CONTENT

    def retrieve(self, username_or_id):
        response = self.session.get(self.get_url('consumers', username_or_id))

        assert response.status_code == OK

        return response.json()


class PluginAdminClient(PluginAdminContract, RestClient):
    def list(self):
        response = self.session.get(self.get_url('plugins'))

        assert response.status_code == OK

        return response.json()

    def retrieve_schema(self, plugin_name):
        response = self.session.get(self.get_url('plugins', plugin_name, 'schema'))

        assert response.status_code == OK

        return response.json()


class KongAdminClient(KongAdminContract):
    def __init__(self, api_url):
        super(KongAdminClient, self).__init__(
            apis=APIAdminClient(api_url),
            consumers=ConsumerAdminClient(api_url),
            plugins=PluginAdminClient(api_url))
