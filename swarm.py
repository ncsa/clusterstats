import re
import docker
import requests
import string
import Config
import json


def get_swarm_namemapping(Env, Type):
    global mapping
    mapping = {}
    prefix = Env + '-' + Type
    config_file_extension = '.' + Type + '-' + Env
    global config
    config = Config.Config(config_file_extension)

    client = docker.DockerClient(base_url=config.swarm_base_url)
    for service in client.services.list():
        if service.name.startswith(prefix):
            key = service.name[1+len(prefix):]
            key = string.replace(key, '_', '')
            key = string.replace(key, '-', '')
            tuple = (key, service.name)

            tuples = mapping.setdefault(Env, {}).setdefault(Type, [])
            tuples.append(tuple)

    '''
    print '\nprint mapping for ', Env, ' ', Type
    for key, service_name in mapping[Env][Type]:
        print key, ", ", service_name
    '''
    return mapping


def get_service_info(instanceName):
    url = config.swarm_http_host + '/api/services/' + instanceName
    r = requests.get(url, auth=(config.swarm_username, config.swarm_password))
    r.raise_for_status()
    metadata = r.json()
    return metadata


def scale_replica (instanceName, newReplica):
    url = '/api/services/' + instanceName + '/scale/' + str(newReplica)
    r = requests.put(url, auth=(config.swarm_username, config.swarm_password))
    r.raise_for_status()

    metadata = get_service_info(instanceName)
    return metadata


if __name__ == '__main__':
    env = 'dev'
    type = 'extractor'
    get_swarm_namemapping(env, type)
    metadata = get_service_info('dev-extractor-ncsa_image_preview')
    print json.dumps(metadata, indent=4)