import base64
import json
import unittest
import mock
import flask

from clusterstats import swarm
from clusterstats.swarm import Swarm
from clusterstats import blueprint_api


# This method will be used for the successful mock of swarm_service_create
def mocked_swarm_service_create_success(*args, **kwargs):
    return True, 100


# This method will be used for the failed mock of swarm_service_create
def mocked_swarm_service_create_failure(*args, **kwargs):
    return False, 100


class SwarmStatsTestCases(unittest.TestCase):
    def setUp(self):
        self.app = flask.Flask('clusterstats')
        usrpass = b'admin:secret'
        b64val = base64.b64encode(usrpass)
        self.headers = {"Authorization": "Basic %s" % str(b64val, 'utf-8')}
        self.data = dict(name='imagemagic', image='ncsapolyglot/converters-imagemagick', env=list(), labels=dict())

    @mock.patch('clusterstats.swarm.Swarm.service_create', side_effect=mocked_swarm_service_create_success)
    def test_blueprint_api_createservice_success(self, mock_create_service):
        with mock.patch.object(Swarm, "__init__", lambda x: None):
            params = json.dumps(self.data)
            swarm.instance = Swarm()
            swarm.instance.services = dict()
            with self.app.test_request_context('/service', method="POST", headers=self.headers, data=params):
                response = blueprint_api.api_services_create()
                self.assertEqual(response.status, '200 OK')

    @mock.patch('clusterstats.swarm.Swarm.service_create', side_effect=mocked_swarm_service_create_failure)
    def test_blueprint_api_createservice_failure(self, mock_create_service_failure):
        with mock.patch.object(Swarm, "__init__", lambda x: None):
            params = json.dumps(self.data)
            swarm.instance = Swarm()
            swarm.instance.services = dict()
            with self.app.test_request_context('/service', method="POST", headers=self.headers, data=params):
                response = blueprint_api.api_services_create()
                self.assertEqual(response.status, '400 BAD REQUEST')

    def test_blueprint_api_createservice_invalid_data(self):
        with mock.patch.object(Swarm, "__init__", lambda x: None):
            swarm.instance = Swarm()
            swarm.instance.services = dict()
            with self.app.test_request_context('/service', method="POST",
                                               headers=self.headers, data=json.dumps(dict())):
                response = blueprint_api.api_services_create()
                self.assertEqual(response.status, '400 BAD REQUEST')

if __name__ == '__main__':
    unittest.main()
