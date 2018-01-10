import docker
import logging
import unittest
import mock
from requests.models import Response

from clusterstats import swarm
from clusterstats.swarm import Swarm
from docker import DockerClient
from docker.models.services import Model

ServiceID = '1111'


# This method will be used for the mock of duplicated service deployment in dockerclient.services.create
def mocked_dockerclient_service_create_duplicate_failure(*args, **kwargs):
    response = Response()
    response.status_code = 2
    response.reason = "rpc error: code = 2 desc = name conflicts with an existing object"
    error = docker.errors.APIError('500 Server Error: Internal Server Error', response)
    raise error


# This method will be used for the successful mock of dockerclient.services.create
def mocked_dockerclient_service_create_success(*args, **kwargs):
    with mock.patch.object(Model, "__init__", lambda x: None):
        service = Model()
        service.attrs = {Model.id_attribute: ServiceID}
        return service


# This method will be used by the mock to replace docker.DockerClient
def mocked_create_dockerclient(*args, **kwargs):
    with mock.patch.object(DockerClient, "__init__", lambda x, y, z: None):
        return DockerClient(None, None)


class SwarmStatsTestCases(unittest.TestCase):
    def setUp(self):
        self.data = dict(name='imagemagic', image='ncsapolyglot/converters-imagemagick', env=list(), labels=dict())

    @mock.patch('docker.DockerClient', side_effect=mocked_create_dockerclient)
    @mock.patch('docker.models.services.ServiceCollection.create',
                side_effect=mocked_dockerclient_service_create_success)
    def test_swarm_service_create_success(self, mock_dockerclient, mock_create_service):
        with mock.patch.object(Swarm, "__init__", lambda x: None):
            swarm.instance = Swarm()
            swarm.instance.swarm_url = ''
            swarm.instance.services = dict()
            swarm.instance.logger = logging.getLogger('swarm')
            (status, context) = swarm.instance.service_create(**self.data)
            self.assertEqual(status, True)
            self.assertEqual(context, ServiceID)

    @mock.patch('docker.DockerClient', side_effect=mocked_create_dockerclient)
    @mock.patch('docker.models.services.ServiceCollection.create',
                side_effect=mocked_dockerclient_service_create_duplicate_failure)
    def test_swarm_service_create_failure(self, mock_dockerclient, mock_create_service):
        with mock.patch.object(Swarm, "__init__", lambda x: None):
            swarm.instance = Swarm()
            swarm.instance.swarm_url = ''
            swarm.instance.services = dict()
            swarm.instance.logger = logging.getLogger('swarm')
            (status, context) = swarm.instance.service_create(**self.data)
            self.assertEqual(status, False)

if __name__ == '__main__':
    unittest.main()
