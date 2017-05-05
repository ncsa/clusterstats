import copy
import datetime
import dateutil.parser
import inspect
import json
import logging
import numbers
import os
import re
import threading
import time

import docker
import docker.errors
import docker.types
import requests.exceptions

import utils


instance = None


def initialize(url, folder='/data', timeout=10, disksize=30 * 1024 * 1024 * 1024):
    global instance

    if instance:
        instance.logger.error("Already created an instance of Swarm")
    else:
        instance = Swarm(url, folder, timeout, disksize)


class Swarm(object):
    """
    Collects all stats for the swarm
    """

    def __init__(self, url, folder='/data', timeout=10, disksize=30 * 1024 * 1024 * 1024):
        """
        Initialize class, start docker client, and threads to collect services, nodes and compute stats

        :param url: url to connect to the docker client 
        :param timeout: timeout for all docker operations
        :param disksize: default disk size for the docker host
        """
        self.threads = dict()
        self.updates = dict()
        self.lock = threading.Lock()

        self.timeouts = {
            'docker': timeout,
            'services': 10,
            'nodes': 10,
            'node': 10,
            'node-full': 60,
            'stats': 10
        }

        self.swarm = {
            'cores': {'total': 0, 'used': 0},
            'memory': {'total': 0, 'used': 0},
            'disk': {'available': 0, 'used': 0, 'data': 0},
            'managers': list(),
            'nodes': {'active': list(), 'drain': list(), 'down': list()},
            'services': list(),
            'containers': list(),
        }
        self.services = dict()
        self.nodes = dict()
        self.containers = dict()

        self.logger = logging.getLogger('swarm')

        # load old data
        self.stats = dict()
        self.folder = folder
        try:
            file = os.path.join(self.folder, 'stats.json')
            if os.path.isfile(file):
                self.stats = json.load(open(file, "rb"))
        except:  # pylint: disable=broad-except
            self.logger.exception("Error reading stats.json")

        # start docker client
        self.swarm_url = url
        self.disksize = disksize
        self.client = docker.DockerClient(base_url=url, version="auto", timeout=self.timeouts['docker'])

        # start thread to collect services
        self.threads['services'] = dict()
        thread = threading.Thread(target=self._collect_services)
        thread.daemon = True
        thread.start()
        self.logger.info("Start collecting services")

        # start thread to collect nodes
        self.threads['nodes'] = dict()
        thread = threading.Thread(target=self._collect_nodes)
        thread.daemon = True
        thread.start()
        self.logger.info("Start collecting nodes")

        # start thread to compute stats
        self.threads['compute'] = dict()
        thread = threading.Thread(target=self._compute)
        thread.daemon = True
        thread.start()
        self.logger.info("Start computing stats")

    def service_create(self, **kwargs):
        client = docker.DockerClient(base_url=self.swarm_url, version='auto')
        try:
            service = client.services.create(**kwargs)
            if service.short_id not in self.services:
                self.services[service.short_id] = {
                    'name': kwargs.get("name", None),
                    'replicas': {'requested': 0, 'running': 0},
                    'containers': list(),
                    'image': kwargs.get("image", None),
                    'env': kwargs.get("env", list()),
                    'nodes': list(),
                    'cores': 0,
                    'memory': 0,
                    'disk': {'used': 0, 'data': 0},
                }
            return True, service.short_id
        except (docker.errors.APIError, AttributeError) as e:
            self.logger.exception("Could not create service.")
            return False, str(e)

    def service_update(self, service):
        self._service_update(service, force=True)

    def service_scale(self, service, count):
        self._service_update(service, count=count)

    def _service_update(self, service, count=None, force=False):
        (k, v) = utils.find_item(self.services, service)
        if k:
            client = docker.APIClient(self.swarm_url, version='auto')
            s = client.inspect_service(k)
            if s and 'Spec' in s and 'TaskTemplate' in s['Spec']:
                spec = s['Spec']
                task = spec['TaskTemplate']

                config = task['ContainerSpec']
                image = config['Image']
                if force:
                    image = re.sub(r'@sha256.*', '', image)
                container_spec = docker.types.ContainerSpec(image,
                                                            command=config.get('Command', None),
                                                            args=config.get('Args', None),
                                                            hostname=config.get('Hostname', None),
                                                            env=config.get('Env', None),
                                                            workdir=config.get('Workdir', None),
                                                            user=config.get('User', None),
                                                            labels=config.get('Labels', None),
                                                            mounts=config.get('Mounts', None),
                                                            stop_grace_period=config.get('StopGracePeriod', None),
                                                            secrets=config.get('Secrets', None))

                if 'Resources' in task:
                    if 'Limits' in task['Resources']:
                        cpu_limit = task['Resources']['Limits'].get('NanoCPUs', None)
                        mem_limit = task['Resources']['Limits'].get('MemoryBytes', None)
                    else:
                        cpu_limit = None
                        mem_limit = None
                    if 'Reservations' in task['Resources']:
                        cpu_reservation = task['Resources']['Reservations'].get('NanoCPUs', None)
                        mem_reservation = task['Resources']['Reservations'].get('MemoryBytes', None)
                    else:
                        cpu_reservation = None
                        mem_reservation = None

                    resources = docker.types.Resources(cpu_limit, mem_limit, cpu_reservation, mem_reservation)
                else:
                    resources = None

                if 'RestartPolicy' in task:
                    config = task['RestartPolicy']
                    restart_policy = docker.types.RestartPolicy(condition=config.get('Condition', 'none'),
                                                                delay=config.get('Delay', 0),
                                                                max_attempts=config.get('MaxAttempts', 0),
                                                                window=config.get('Window', 0))
                else:
                    restart_policy = None

                if 'LogDriver' in task:
                    config = task['LogDriver']
                    log_driver = docker.types.DriverConfig(config['Name'],
                                                           options=config.get('Options', None))
                else:
                    log_driver = None

                force_update = task.get('ForceUpdate', 0)
                if force:
                    force_update += 1
                task_template = docker.types.TaskTemplate(container_spec,
                                                          resources=resources,
                                                          restart_policy=restart_policy,
                                                          placement=task.get('Placement', None),
                                                          log_driver=log_driver,
                                                          force_update=force_update)

                if count:
                    mode = docker.types.ServiceMode("replicated", int(count))
                    # TODO bug in docker library, see https://github.com/docker/docker-py/issues/1572
                    if int(count) == 0:
                        mode.get('replicated')['Replicas'] = 0
                else:
                    mode = docker.types.ServiceMode("replicated", utils.get_item(spec, 'Mode.Replicated.Replicas', 0))

                if 'UpdateConfig' in spec:
                    config = spec['EndpointSpec']
                    update_config = docker.types.UpdateConfig(config.get('Parallelism', 0),
                                                              config.get('Delay', None),
                                                              config.get('FailureAction', 'continue'),
                                                              config.get('Monitor', None),
                                                              config.get('MaxFailureRatio', None))
                else:
                    update_config = None

                if 'EndpointSpec' in spec:
                    config = spec['EndpointSpec']
                    endpoint_spec = docker.types.EndpointSpec(config.get('Mode', None),
                                                              config.get('Ports', None))
                else:
                    endpoint_spec = None

                if client.update_service(k,
                                         version=s['Version']['Index'],
                                         task_template=task_template,
                                         name=spec['Name'],
                                         labels=spec.get('Labels', None),
                                         mode=mode,
                                         update_config=update_config,
                                         networks=spec.get('Networks', None),
                                         endpoint_spec=endpoint_spec):
                    if count:
                        v['replicas']['requested'] = int(count)
                    return True, 'OK'
                else:
                    return False, 'Could not update service %s.' % service

            else:
                return False, 'service "%s" not found' % service
        else:
            return False, 'service "%s" not found' % service

    def service_log(self, service, lines=10):
        (_, s) = utils.find_item(self.services, service)
        if not s:
            return None

        # TODO work with generator
        all_logs = []
        for c in s['containers']:
            for line in self.container_log(c, lines, True).split("\n"):
                pieces = line.split(maxsplit=1)
                if len(pieces) == 2:
                    all_logs.append({'time': pieces[0], 'container': c, 'log': pieces[1]})
        sorted_logs = sorted(all_logs, key=lambda x: x['time'])

        if lines != 'all':
            sorted_logs = sorted_logs[-lines:]

        log = ""
        for line in sorted_logs:
            log += "%s | %s | %s\n" % (line['time'], line['container'], line['log'])
        # for line in sorted_logs:
        #     pieces = line.split(maxsplit=1)
        #     if len(pieces) == 2:
        #         log += pieces[1] + "\n"

        return log

    def container_log(self, container, lines=10, timestamps=False):
        if lines == 'all':
            lines = 100

        (k, v) = utils.find_item(self.containers, container)
        if not k:
            return None

        node = self.nodes[v['node']]
        if 'url' in node:
            result = ""
            client = docker.APIClient(base_url=node['url'], version="auto", timeout=self.timeouts['docker'])
            try:
                log = client.logs(k, stdout=True, stderr=True, follow=False, timestamps=timestamps, tail=lines)
                if inspect.isgenerator(log):
                    for row in log:
                        # TODO work with generator
                        result += row.decode('utf-8')
                else:
                    result = log.decode('utf-8')
            except docker.errors.NotFound:
                self.logger.info("Trying to get log from container '%s' that no longer exists." % container)
                result = "Countainer %s is no longer running." % container
        else:
            result = "Could not connect to docker host, no logs returned for %s." % container
        return result

    def _collect_services(self):
        """
        Collect all services running in swarm 
        """
        while True:
            if 'services' not in self.threads:
                break

            try:
                service_ids = list(self.services.keys())
                for service in self.client.services.list():
                    if service.short_id not in self.services:
                        self.swarm['services'].append(service.short_id)
                        with self.lock:
                            self.services[service.short_id] = {
                                'name': service.name,
                                'replicas': {'requested': 0, 'running': 0},
                                'containers': list(),
                                'image': None,
                                'env': list(),
                                'nodes': list(),
                                'cores': 0,
                                'memory': 0,
                                'disk': {'used': 0, 'data': 0},
                            }
                            self.logger.info("Adding service %s [id=%s]" % (service.name, service.short_id))
                    else:
                        service_ids.remove(service.short_id)
                    v = utils.get_item(service.attrs, 'Spec.Mode.Replicated.Replicas', 0)
                    self.services[service.short_id]['replicas']['requested'] = v
                    image = utils.get_item(service.attrs, 'Spec.TaskTemplate.ContainerSpec.Image', None)
                    if image:
                        image = re.sub(r"@sha.*$", "", image)
                    self.services[service.short_id]['image'] = image
                    self.services[service.short_id]['env'] = utils.get_item(service.attrs,
                                                                            'Spec.TaskTemplate.ContainerSpec.Env',
                                                                            list())
                with self.lock:
                    for key in service_ids:
                        service = self.services.pop(key, None)
                        if key in self.swarm['services']:
                            self.swarm['services'].remove(key)
                        if service:
                            self.logger.info("Removing service %s [id=%s]" % (service['name'], key))

                self.updates['services'] = utils.get_timestamp()
            except:  # pylint: disable=broad-except
                self.logger.warning("Error collecting services.")
            time.sleep(self.timeouts['services'])

    def _collect_nodes(self):
        """
        Collect all nodes in swarm. Each node discovered that is alive will cause a new thread to 
        be started that will collect information about the node (such as containers).
        """
        while True:
            if 'nodes' not in self.threads:
                break
            try:
                node_ids = list(self.nodes.keys())
                for node in self.client.nodes.list():
                    attrs = node.attrs

                    if node.short_id not in node_ids:
                        description = attrs['Description']
                        resources = description['Resources']
                        cores = int(resources['NanoCPUs'] / 1000000000)
                        memory = resources['MemoryBytes']
                        disk = self.disksize
                        hostname = description['Hostname']
                        if 'Addr' in attrs['Status']:
                            if attrs['Status']['Addr'] == "127.0.0.1":
                                node_url = self.swarm_url
                            else:
                                node_url = 'tcp://%s:2375' % attrs['Status']['Addr']
                        else:
                            node_url = None

                        with self.lock:
                            self.nodes[node.short_id] = {
                                'name': hostname,
                                'url': node_url,
                                'cores': {'total': cores, 'used': 0},
                                'memory': {'total': memory, 'used': 0},
                                'disk': {'available': disk, 'used': 0, 'data': 0},
                                'status': None,
                                'services': list(),
                                'containers': list()
                            }
                    else:
                        node_ids.remove(node.short_id)

                    n = self.nodes[node.short_id]
                    if attrs['Spec']['Role'] == 'manager':
                        if node.short_id not in self.swarm['managers']:
                            self.swarm['managers'].append(node.short_id)
                    oldstatus = n['status']
                    newstatus = attrs['Spec']['Availability']
                    if newstatus != oldstatus:
                        self.nodes[node.short_id]['status'] = newstatus

                        if oldstatus:
                            self.swarm['nodes'][oldstatus].remove(node.short_id)
                        if oldstatus == 'active':
                            self.swarm['cores']['total'] -= n['cores']['total']
                            self.swarm['memory']['total'] -= n['memory']['total']
                            self.swarm['disk']['available'] -= n['disk']['available']

                            self.threads.pop(node.short_id, None)
                            for k, v in self.containers.items():
                                if v['node'] == node.short_id:
                                    self.threads.pop(k, None)
                                    self.logger.info("Stopping container collection %s [id=%s]" % (v['name'], k))
                            self.logger.info("Stopping node collection %s [id=%s]" % (n['name'], node.short_id))

                        if newstatus:
                            if newstatus not in self.swarm['nodes']:
                                self.swarm['nodes'][newstatus] = list()
                            self.swarm['nodes'][newstatus].append(node.short_id)
                        if newstatus == 'active':
                            self.swarm['cores']['total'] += n['cores']['total']
                            self.swarm['memory']['total'] += n['memory']['total']
                            self.swarm['disk']['available'] += n['disk']['available']

                            self.threads[node.short_id] = dict()
                            thread = threading.Thread(target=self._collect_node, args=[node.short_id])
                            thread.daemon = True
                            thread.start()
                            self.logger.info("Starting collection node %s [id=%s]" % (n['name'], node.short_id))

                with self.lock:
                    for key in node_ids:
                        node = self.nodes.pop(key, None)
                        for k, v in self.containers.items():
                            if v['node'] == node.short_id:
                                self.threads.pop(k, None)
                                self.logger.info("Stopping container collection %s [id=%s]" % (v['name'], k))
                        if node:
                            self.logger.info("Removing node %s [id=%s]" % (node['name'], key))

                self.updates['nodes'] = utils.get_timestamp()
            except:  # pylint: disable=broad-except
                self.logger.warning("Error collecting nodes.")
            time.sleep(self.timeouts['nodes'])

    def _collect_node(self, node_id):
        """
        Collect all information on a node. This will collect all containers on the node, and start monitoring them.

        :param node_id: the id of the node to be monitored 
        """
        node = self.nodes[node_id]

        client = docker.DockerClient(base_url=node['url'], version="auto", timeout=self.timeouts['docker'])
        next_full = time.time() + self.timeouts['node']
        while True:
            if node_id not in self.threads:
                break
            try:
                if time.time() > next_full:
                    next_full = time.time() + self.timeouts['node-full']
                    size = True
                else:
                    size = False

                container_ids = list(node['containers'])
                for container in client.api.containers(size=size):
                    container_id = container['Id'][:10]
                    if container_id in container_ids:
                        container_ids.remove(container_id)
                    else:
                        node['containers'].append(container_id)
                    if container_id not in self.swarm['containers']:
                        self.swarm['containers'].append(container_id)
                    if container_id not in self.containers:
                        with self.lock:
                            self.containers[container_id] = {
                                'name': ",".join(container['Names']),
                                'state': None,
                                'status': container['Status'],
                                'env': list(),
                                'cores': 0,
                                'memory': 0,
                                'disk': {'used': 0, 'data': 0},
                                'service': None,
                                'node': node_id
                            }
                            self.logger.info("Adding container %s [id=%s] on node %s" % (",".join(container['Names']),
                                                                                         container_id, node_id))
                    c = self.containers[container_id]

                    labels = container['Labels']
                    if 'com.docker.swarm.service.id' in labels and 'com.docker.swarm.service.name' in labels:
                        service_id = labels['com.docker.swarm.service.id'][:10]
                        c['service'] = service_id
                        if service_id in self.services:
                            if container_id not in self.services[service_id]['containers']:
                                self.services[service_id]['containers'].append(container_id)
                                self.services[service_id]['replicas']['running'] += 1
                            if node_id not in self.services[service_id]['nodes']:
                                self.services[service_id]['nodes'].append(node_id)
                        if service_id not in node['services']:
                            node['services'].append(service_id)

                    c['status'] = container['Status']
                    c['env'] = utils.get_item(container, 'Spec.TaskTemplate.ContainerSpec.Env', list())

                    # update size stats
                    if size:
                        # 'SizeRootFs' == size of all files
                        # 'SizeRw' == size of all files added to image
                        diff = container.get('SizeRootFs', 0) - c['disk']['used']
                        self.swarm['disk']['used'] += diff
                        node['disk']['used'] += diff
                        self.services[c['service']]['disk']['used'] += diff
                        c['disk']['used'] = container.get('SizeRootFs', 0)
                        diff = container.get('SizeRw', 0) - c['disk']['data']
                        self.swarm['disk']['data'] += diff
                        node['disk']['data'] += diff
                        self.services[c['service']]['disk']['data'] += diff
                        c['disk']['data'] = container.get('SizeRw', 0)

                    # collect container stats if needed
                    oldstate = c['state']
                    newstate = container['State']
                    if oldstate != newstate:
                        c['state'] = newstate
                        if oldstate == 'running':
                            self.threads.pop(container_id, None)
                            self.swarm['containers'].append(container_id)
                            node['containers'].append(container_id)
                            self.containers.pop(container_id, None)
                            self.logger.info("Stopping container collection %s [id=%s]" % (c['name'], container_id))
                        else:
                            self.swarm['containers'].remove(container_id)
                            node['containers'].remove(container_id)

                            self.threads[container_id] = dict()
                            x = client.containers.get(container_id)
                            thread = threading.Thread(target=self._collect_container, args=[x])
                            thread.daemon = True
                            thread.start()
                            self.logger.info("Starting container collection %s [id=%s]" % (c['name'], container_id))

                with self.lock:
                    for key in container_ids:
                        self.threads.pop(key, None)
                        container = self.containers.pop(key, None)
                        if key in node['containers']:
                            node['containers'].remove(key)
                        if key in self.swarm['containers']:
                            self.swarm['containers'].remove(key)
                        if container:
                            service_id = container['service']
                            self.services[service_id]['containers'].remove(key)
                            self.services[service_id]['replicas']['running'] -= 1
                            self.services[service_id]['nodes'].append(node_id)
                            node['services'].remove(service_id)
                            self.logger.info("Removing container %s [id=%s] on node %s" % (container['name'],
                                                                                           key, node_id))

                node['updated'] = utils.get_timestamp()
            except requests.exceptions.ReadTimeout:
                self.logger.info("Timeout collecting containers for node %s." % node_id)
            except:  # pylint: disable=broad-except
                self.logger.exception("Error collecting containers for node %s." % node_id)

            time.sleep(self.timeouts['node'])
        self.logger.info("Stop collecting for node %s." % node_id)

    def _collect_container(self, container):
        """
        Collect statistics (CPU, Memory) for the container.
        :param container: the container to be monitored
        """
        mystats = self.threads[container.short_id]
        c = self.containers[container.short_id]
        while True:
            if container.short_id not in self.threads:
                break
            try:
                first_run = True
                generator = container.stats(decode=True, stream=True)
                for stats in generator:
                    if container.short_id not in self.threads:
                        break
                    if first_run:
                        first_run = False
                        continue

                    cpu_percent = None
                    cpu_stats = stats['cpu_stats']
                    precpu_stats = stats['precpu_stats']
                    if 'system_cpu_usage' in cpu_stats and 'system_cpu_usage' in precpu_stats:
                        cpu_usage = cpu_stats['cpu_usage']
                        precpu_usage = precpu_stats['cpu_usage']
                        system_delta = float(cpu_stats['system_cpu_usage']) - float(precpu_stats['system_cpu_usage'])
                        cpu_delta = float(cpu_usage['total_usage']) - float(precpu_usage['total_usage'])
                        if system_delta > 0.0 and cpu_delta > 0.0:
                            cpu_percent = round((cpu_delta / system_delta) * float(len(cpu_usage['percpu_usage'])), 2)

                    if cpu_percent:
                        c['cores'] = cpu_percent
                    mystats['cores'] = cpu_percent

                    memory = stats['memory_stats'].get('usage', None)
                    if memory:
                        memory = int(memory)
                        c['memory'] = memory
                    mystats['memory'] = memory
            except docker.errors.NotFound:
                self.logger.info("Container %s is gone?" % container.short_id)
            except docker.errors.APIError as e:
                self.logger.info("Docker exception %s : %s" % (container.short_id, e.explanation))
            except requests.exceptions.ReadTimeout:
                self.logger.info("Timeout getting stats for %s" % container.short_id)
            except:  # pylint: disable=broad-except
                self.logger.exception("Error collecting stats for %s" % container.short_id)

            time.sleep(self.timeouts['stats'])

    def _compute(self):
        while True:
            if 'compute' not in self.threads:
                break
            try:
                swarm_stats = {'cores': 0, 'memory': 0, 'disk': 0, 'data': 0}
                nodes_stats = {k: {'cores': 0, 'memory': 0, 'disk': 0, 'data': 0} for k in self.nodes.keys()}
                services_stats = {k: {'cores': 0, 'memory': 0, 'disk': 0, 'data': 0} for k in self.services.keys()}

                # compute cores/memory
                with self.lock:
                    for k, v in self.containers.items():
                        s = self.threads.get(k)
                        if s:
                            if s['cores']:
                                swarm_stats['cores'] += s['cores']
                                if v['node']:
                                    nodes_stats[v['node']]['cores'] += s['cores']
                                if v['service']:
                                    services_stats[v['service']]['cores'] += s['cores']
                            if s['memory']:
                                swarm_stats['memory'] += s['memory']
                                if v['node']:
                                    nodes_stats[v['node']]['memory'] += s['memory']
                                if v['service']:
                                    services_stats[v['service']]['memory'] += s['memory']
                        swarm_stats['disk'] += v['disk']['used']
                        swarm_stats['data'] += v['disk']['data']
                        if v['node'] in nodes_stats:
                            nodes_stats[v['node']]['disk'] += v['disk']['used']
                            nodes_stats[v['node']]['data'] += v['disk']['data']
                        if v['service'] in services_stats:
                            services_stats[v['service']]['disk'] += v['disk']['used']
                            services_stats[v['service']]['data'] += v['disk']['data']

                # swarm stats
                self.swarm['cores']['used'] = swarm_stats['cores']
                self.swarm['memory']['used'] = swarm_stats['memory']
                self.swarm['disk']['used'] = swarm_stats['disk']
                self.swarm['disk']['data'] = swarm_stats['data']
                deepcopy = copy.deepcopy(self.swarm)
                deepcopy.pop("managers")
                deepcopy['containers'] = len(deepcopy['containers'])
                deepcopy['services'] = len(deepcopy['services'])
                deepcopy['nodes'] = len(deepcopy['nodes']['active'])

                self._compute_bin('swarm', deepcopy, '1hour')
                self._compute_bin('swarm', deepcopy, '6hour')
                self._compute_bin('swarm', deepcopy, '24hour')
                self._compute_bin('swarm', deepcopy, 'week')
                self._compute_bin('swarm', deepcopy, 'month')
                self._compute_bin('swarm', deepcopy, 'year')
                self._compute_bin('swarm', deepcopy, 'all')

                # node stats
                for k, v in nodes_stats.items():
                    self.nodes[k]['cores']['used'] = v['cores']
                    self.nodes[k]['memory']['used'] = v['memory']
                    self.nodes[k]['disk']['used'] = v['disk']
                    self.nodes[k]['disk']['data'] = v['data']

                # service stats
                for k, v in services_stats.items():
                    self.services[k]['cores'] = v['cores']
                    self.services[k]['memory'] = v['memory']
                    self.services[k]['disk']['used'] = v['disk']
                    self.services[k]['disk']['data'] = v['data']

                # save
                with open(os.path.join(self.folder, 'stats.json'), "w") as f:
                    json.dump(self.stats, f)
            except:  # pylint: disable=broad-except
                self.logger.exception("Error computing stats.")

            time.sleep(self.timeouts['stats'])

    def _compute_bin(self, what, data, period):
        now = datetime.datetime.utcnow()

        if period == '1hour':
            time_bin = now.replace(second=0, microsecond=0)
            delta = datetime.timedelta(hours=1)
        elif period == '6hour':
            time_bin = now.replace(minute=now.minute // 5 * 5, second=0, microsecond=0)
            delta = datetime.timedelta(hours=6)
        elif period == '24hour':
            time_bin = now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0)
            delta = datetime.timedelta(days=1)
        elif period == 'week':
            time_bin = now.replace(hour=now.hour // 2 * 2, minute=0, second=0, microsecond=0)
            delta = datetime.timedelta(days=7)
        elif period == 'month':
            time_bin = now.replace(hour=now.hour // 12 * 12, minute=0, second=0, microsecond=0)
            delta = datetime.timedelta(days=30)
        elif period == 'year':
            if now.weekday() < 3:
                # monday, tuesday, wednesday
                days = datetime.timedelta(days=now.weekday())
                time_bin = now.replace(hour=0, minute=0, second=0, microsecond=0) - days
            else:
                # thursday, friday, saturday, sunday
                days = datetime.timedelta(days=now.weekday() - 3)
                time_bin = now.replace(hour=0, minute=0, second=0, microsecond=0) - days
            delta = datetime.timedelta(days=365)
        elif period == 'all':
            if now.day < 15:
                time_bin = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                time_bin = now.replace(day=15, hour=0, minute=0, second=0, microsecond=0)
            delta = None
        else:
            self.logger.warning("Could not compute stats for % for period=%s" % (what, period))
            return

        data = copy.deepcopy(data)

        if what not in self.stats:
            self.stats[what] = dict()
        if period not in self.stats[what]:
            self.stats[what][period] = list()

        data['time'] = time_bin.isoformat()
        data['_count'] = 1
        for x in self.stats[what][period]:
            if x['time'] == data['time']:
                self._compute_average(x, data, x['_count'])
                x['_count'] += 1
                break
        else:
            self.stats[what][period].append(data)

        if delta:
            while len(self.stats[what][period]) > 0:
                firstdate = dateutil.parser.parse(self.stats[what][period][0]['time'])
                if (time_bin - firstdate) > delta:
                    self.stats[what][period].pop(0)
                else:
                    break

    def _compute_average(self, cumalative, data, count):
        for k, v in data.items():
            if k == '_count' or k == 'time':
                continue
            if k in cumalative:
                if isinstance(v, numbers.Number):
                    try:
                        cumalative[k] = (cumalative[k] * count + v) / (count + 1)
                    except:  # pylint: disable=broad-except
                        self.logger.exception("Could not compute average for %s" % k)
                elif isinstance(v, dict):
                    self._compute_average(cumalative[k], v, count)
                else:
                    self.logger.debug("not a dict or number %s" % k)
                    cumalative[k] = v
            else:
                cumalative[k] = v
