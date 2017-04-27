#!/usr/bin/env python3

import argparse
import copy
import datetime
import inspect
import functools
import json
import logging
import logging.config
import numbers
import os
import sys
import threading
import time
import urllib

import dateutil.parser
import docker
import docker.types
import docker.errors
import flask
import flask.ext
import flask_cors
from werkzeug.contrib.fixers import ProxyFix

software_version = '1.0'

hide_env = True
logger = None
app = None
swarm_url = None
threads_stats = dict()
lock = threading.Lock()
context = '/'
data_folder = '.'
refresh = 60
docker_disk = 30 * 1024 * 1024 * 1024
timeouts = {
    'services': 10,
    'nodes': 10,
    'node': 10,
    'node-full': 60,
    'stats': 10,
    'docker': 10
}

version = {
    'version': software_version,
    'build': os.getenv('BUILD', 'unknown'),
    'updated': {'services': None, 'nodes': None, 'containers': None}
}
stats = dict()
swarm = {
    'cores': {'total': 0, 'used': 0},
    'memory': {'total': 0, 'used': 0},
    'disk': {'available': 0, 'used': 0, 'data': 0},
    'managers': list(),
    'nodes': {'active': list(), 'drain': list(), 'down': list()},
    'services': list(),
    'containers': list()
}

services = dict()
nodes = dict()
containers = dict()

bp_api = flask.Blueprint('api',  __name__)
bp_html = flask.Blueprint('html',  __name__, static_folder='static', template_folder='templates')


def main():
    global logger, data_folder, docker_disk, app, swarm_url, refresh

    # parse command line arguments
    parser = argparse.ArgumentParser(description='Extractor registration system.')
    parser.add_argument('--context', '-c', default=None,
                        help='application context (default=extractors)')
    parser.add_argument('--datadir', '-d', default=os.getenv("DATADIR", '.'),
                        help='location to store all data')
    parser.add_argument('--disk', default=docker_disk,
                        help='disk space free on each docker node')
    parser.add_argument('--logging', '-l', default=os.getenv("LOGGER", None),
                        help='file or logging coonfiguration (default=None)')
    parser.add_argument('--port', '-p', type=int, default=9999,
                        help='port the server listens on (default=9999)')
    parser.add_argument('--refresh', '-r', default=60,
                        help='refresh timeout for containers')
    parser.add_argument('--swarm', '-s', default=os.getenv("SWARM", None),
                        help='swarm ipaddress:port')
    parser.add_argument('--timeout', '-t', default=5,
                        help='timeout for docker operations')
    parser.add_argument('--version', action='version', version='%(prog)s version=' + software_version)
    args = parser.parse_args()

    # setup logging
    config_logger(args.logging)
    logger = logging.getLogger('extractors')

    # load data
    data_folder = args.datadir
    load_data()

    # set up collector
    refresh = args.refresh
    if args.swarm and args.swarm != "":
        if args.swarm.startswith('unix://'):
            swarm_url = args.swarm
        elif args.swarm.startswith('tcp://'):
            swarm_url = args.swarm
        elif ':' in args.swarm:
            swarm_url = 'tcp://' + args.swarm
        else:
            swarm_url = 'tcp://' + args.swarm + ':2375'
    else:
        logger.error("No swarm or node specified")
        parser.print_help()
        sys.exit(-1)
    collect_stats(swarm_url)

    # setup app
    app = flask.Flask('swarmstats')
    app.wsgi_app = ProxyFix(app.wsgi_app)
    if args.context:
        context = args.context.rstrip('/')
        app.register_blueprint(bp_html, url_prefix=context)
        app.register_blueprint(bp_api, url_prefix=context + '/api')
    else:
        app.register_blueprint(bp_html, url_prefix=None)
        app.register_blueprint(bp_api, url_prefix='/api')

    # setup cors
    flask_cors.CORS(app)

    # start the app
    app.run(host="0.0.0.0", port=args.port, threaded=True)


# ----------------------------------------------------------------------
# HELPER FUNCTIONS
# ----------------------------------------------------------------------

def config_logger(config_info):
    global logger

    if config_info:
        if os.path.isfile(config_info):
            if config_info.endswith('.json'):
                with open(config_info, 'r') as f:
                    config = json.load(f)
                    logging.config.dictConfig(config)
            else:
                logging.config.fileConfig(config_info)
        else:
            config = json.load(config_info)
            logging.config.dictConfig(config)
    else:
        logging.basicConfig(format='%(asctime)-15s %(levelname)-7s : %(name)s - %(message)s',
                            level=logging.INFO)
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        logger = logging.getLogger('extractors')
        logger.setLevel(logging.DEBUG)


def get_stats(what, period):
    '''
    From the stats return the stats for the right period. If no period is given it will retunr
    a list of the periods.
    :param what: the stats to return, swar, container id, service id, etc.
    :param period: period of stats to return 4hour, ...
    :return: stats for that period, or list of periods
    '''
    global stats

    if what in stats:
        if not period:
            return flask.jsonify(list(stats[what].keys()))
        elif period in stats[what]:
            return flask.jsonify(stats[what][period])
        else:
            return flask.Response('no stats found for %s in %s' % (period, what), status=404)
    else:
        return flask.Response('no stats found for %s' % what, status=404)


def find_item(where, id):
    value = where.get(id, None)
    if value:
        return (id, value)
    if len(id) > 10:
        key = id[:10]
        if key in where:
            return (key, where[key])
    for k, v in where.items():
        if v['name'] == id:
            return (k, v)
    return (None, None)


def get_item(where, key, defaultvalue):
    x = where
    for k in key.split("."):
        if k in x:
            x = x[k]
        else:
            return defaultvalue
    return x


def get_timestamp():
    return datetime.datetime.utcnow().isoformat(timespec='seconds') + "Z"


def check_auth(username, password):
    if os.path.isfile('/run/secrets/' + username):
        with open('/run/secrets/' + username, 'r') as secret:
            return secret.readline() == password
    else:
        return password == "browndog"


def requires_user(*users):
    def wrapper(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            auth = flask.request.authorization
            if not auth or not auth.username or not auth.password or not check_auth(auth.username, auth.password):
                return flask.Response(headers={'WWW-Authenticate': 'Basic realm="swarmstats"'}, status=401)
            elif auth.username not in users:
                return flask.abort(403)
            else:
                return f(*args, **kwargs)
        return wrapped
    return wrapper


# ----------------------------------------------------------------------
# HTML PAGES
# ----------------------------------------------------------------------

@bp_html.route('/', defaults={'page': 'dashboard'})
@bp_html.route('/<page>')
@requires_user("admin", "viewer")
def html_page(page):
    global app
    return app.send_static_file('%s.html' % page)


@bp_html.route('/services/<service>/logs')
@requires_user("admin", "viewer")
def html_services_logs(service):
    global services

    (k, v) = find_item(services, service)
    return flask.render_template('logs.html', service_id=k, service_name=v['name'], containers=v['containers'])


# ----------------------------------------------------------------------
# VERSION API IMPLEMENTATION
# ----------------------------------------------------------------------

@bp_api.route('/version')
@requires_user("admin", "viewer")
def api_version():
    global version, app, context

    if 'routes' not in version:
        routes = list()
        for rule in app.url_map.iter_rules():
            options = {}
            for arg in rule.arguments:
                options[arg] = "[{0}]".format(arg)
            url = urllib.parse.unquote(flask.url_for(rule.endpoint, **options))
            if url not in routes:
                routes.append(urllib.parse.unquote(url))
        routes.sort()
        version['routes'] = routes
    version['styles'] = flask.url_for('static', filename='style.css')
    return flask.jsonify(version)


# ----------------------------------------------------------------------
# SWARM API IMPLEMENTATION
# ----------------------------------------------------------------------

@bp_api.route('/swarm')
@requires_user("admin", "viewer")
def api_swarm():
    global swarm
    if flask.request.args.get('full'):
        return flask.jsonify(swarm)
    else:
        result = copy.deepcopy(swarm)
        result['containers'] = len(result['containers'])
        result['services'] = len(result['services'])
        result['nodes'] = len(result['nodes']['active'])
        return flask.jsonify(result)


@bp_api.route('/swarm/stats', defaults={'period': None})
@bp_api.route('/swarm/stats/<period>')
@requires_user("admin", "viewer")
def api_swarm_stats(period):
    return get_stats('swarm', period)


# ----------------------------------------------------------------------
# NODES API IMPLEMENTATION
# ----------------------------------------------------------------------

@bp_api.route('/nodes', defaults={'node': None})
@bp_api.route('/nodes/<node>')
@requires_user("admin", "viewer")
def api_nodes(node):
    global nodes

    if node:
        (_, v) = find_item(nodes, node)
        if v:
            return flask.jsonify(v)
        else:
            return flask.Response('node "%s" not found' % node, status=404)
    else:
        if flask.request.args.get('full'):
            return flask.jsonify(nodes)
        else:
            result = {k: v['name'] for k, v in nodes.items()}
            return flask.jsonify(result)


@bp_api.route('/nodes/<node>/stats', defaults={'period': None})
@bp_api.route('/nodes/<node>/stats/<period>')
@requires_user("admin", "viewer")
def api_nodes_stats(node, period):
    global nodes

    (k, _) = find_item(nodes, node)
    if k:
        return get_stats(k, period)
    else:
        return flask.Response('node "%s" not found' % node, status=404)


# ----------------------------------------------------------------------
# SERVICES API IMPLEMENTATION
# ----------------------------------------------------------------------

@bp_api.route('/services', defaults={'service': None})
@bp_api.route('/services/<service>')
@requires_user("admin", "viewer")
def api_services(service=None):
    global services

    if service:
        (_, v) = find_item(services, service)
        if v:
            if not hide_env or flask.request.authorization.username == 'admin':
                return flask.jsonify(v)
            else:
                v = copy.copy(v)
                v.pop('env', None)
                return flask.jsonify(v)
        else:
            return flask.Response('service "%s" not found' % service, status=404)
    else:
        if flask.request.args.get('full'):
            if not hide_env or flask.request.authorization.username == 'admin':
                return flask.jsonify(services)
            else:
                results = dict()
                for k, v in services.items():
                    results[k] = copy.copy(v)
                    results[k].pop('env', None)
                return flask.jsonify(results)
        else:
            results = {k: v['name'] for k, v in services.items()}
            return flask.jsonify(results)


@bp_api.route('/services/<service>/logs')
@requires_user("admin", "viewer")
def api_services_logs(service):
    global services

    lines = int(flask.request.args.get('lines', '20'))
    if lines == 0:
        lines = 'all'
    log = service_log(service, lines=lines)
    if log or log == '':
        return flask.Response(log, mimetype='text/ascii')
    else:
        return flask.Response('No logs found for %s' % service, status=404)


@bp_api.route('/services/<service>/restart', methods=['POST'])
@requires_user("admin")
def api_services_restart(service):
    global services

    (id, v) = find_item(services, service)
    if id and v:
        replicas = v['replicas']
        api_services_scale(id, 0)
        time.sleep(30)
        api_services_scale(id, replicas)
    else:
        return flask.Response('service "%s" not found' % service, status=404)


@bp_api.route('/services/<service>/scale/<count>', methods=['PUT'])
@requires_user("admin")
def api_services_scale(service, count):
    global services, swarm, swarm_url

    if swarm_url:
        (id, v) = find_item(services, service)
        if id:
            client = docker.APIClient(swarm_url)
            s = client.inspect_service(id)
            if s and 'Spec' in s and 'TaskTemplate' in s['Spec']:
                spec = s['Spec']
                task = spec['TaskTemplate']

                config = task['ContainerSpec']
                container_spec = docker.types.ContainerSpec(config['Image'],
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

                task_template = docker.types.TaskTemplate(container_spec,
                                                          resources=resources,
                                                          restart_policy=restart_policy,
                                                          placement=task.get('Placement', None),
                                                          log_driver=log_driver,
                                                          force_update=task.get('ForceUpdate', 0))

                mode = docker.types.ServiceMode("replicated", int(count))
                # TODO bug in docker library, see https://github.com/docker/docker-py/issues/1572
                if int(count) == 0:
                    mode.get('replicated')['Replicas'] = 0

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

                client.update_service(id,
                                      version=s['Version']['Index'],
                                      task_template=task_template,
                                      name=spec['Name'],
                                      labels=spec['Labels'],
                                      mode=mode,
                                      update_config=update_config,
                                      networks=spec['Networks'],
                                      endpoint_spec=endpoint_spec)

                v['replicas']['requested'] = int(count)
                return flask.Response('', status=204)
            else:
                return flask.Response('service "%s" not found' % service, status=404)
        else:
            return flask.Response('service "%s" not found' % service, status=404)
    else:
        return flask.Response('Could not scale service %s, not connected to swarm' % service, status=404)


@bp_api.route('/services/<service>/stats', defaults={'period': None})
@bp_api.route('/services/<service>/stats/<period>')
@requires_user("admin", "viewer")
def api_services_stats(service, period):
    global services

    (k, _) = find_item(services, service)
    if k:
        return get_stats(k, period)
    else:
        return flask.Response('service "%s" not found' % service, status=404)


# ----------------------------------------------------------------------
# CONTAINERS API IMPLEMENTATION
# ----------------------------------------------------------------------

@bp_api.route('/containers', defaults={'container': None})
@bp_api.route('/containers/<container>')
@requires_user("admin", "viewer")
def api_containers(container=None):
    global containers

    if container:
        (_, v) = find_item(containers, container)
        if v:
            if not hide_env or flask.request.authorization.username == 'admin':
                return flask.jsonify(v)
            else:
                v = copy.copy(v)
                v.pop('env', None)
                return flask.jsonify(v)
        else:
            return flask.Response('container "%s" not found' % container, status=404)
    else:
        if flask.request.args.get('full'):
            if not hide_env or flask.request.authorization.username == 'admin':
                return flask.jsonify(containers)
            else:
                results = dict()
                for k, v in containers.items():
                    results[k] = copy.copy(v)
                    results[k].pop('env', None)
                return flask.jsonify(results)
        else:
            results = {k: v['name'] for k, v in containers.items()}
            return flask.jsonify(results)


@bp_api.route('/containers/<container>/logs')
@requires_user("admin", "viewer")
def api_containers_logs(container):
    global containers

    lines = int(flask.request.args.get('lines', '20'))
    if lines == 0:
        lines = 'all'
    log = container_log(container, lines=lines)
    if log or log == '':
        return flask.Response(log, mimetype='text/ascii')
    else:
        return flask.Response('No logs found for %s' % container, status=404)


@bp_api.route('/containers/<container>/stats', defaults={'period': None})
@bp_api.route('/containers/<container>/stats/<period>')
@requires_user("admin", "viewer")
def api_containers_stats(container, period):
    global containers

    (k, _) = find_item(containers, container)
    if k:
        return get_stats(k, period)
    else:
        return flask.Response('container "%s" not found' % container, status=404)


# ----------------------------------------------------------------------
# LOG COLLECTOR
# ----------------------------------------------------------------------

def service_log(service, lines=10):
    global services, nodes, containers, swarm_url

    (_, s) = find_item(services, service)
    if not s:
        return None

    all_logs = []
    for c in s['containers']:
        for line in container_log(c, lines, True).split("\n"):
            pieces = line.split(maxsplit=1)
            if len(pieces) == 2:
                all_logs.append({'time': pieces[0], 'container': c, 'log': pieces[1]})
    sorted_logs = sorted(all_logs, key=lambda log: log['time'])

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


def container_log(container, lines=10, timestamps=False):
    global nodes, containers, timeouts

    if lines == 'all':
        lines = 100

    (k, v) = find_item(containers, container)
    if not k:
        return None

    node = nodes[v['node']]
    if 'url' in node:
        result = ""
        client = docker.APIClient(base_url=node['url'], version="auto", timeout=timeouts['docker'])
        try:
            log = client.logs(k, stdout=True, stderr=True, follow=False, timestamps=timestamps, tail=lines)
            if inspect.isgenerator(log):
                for row in log:
                    logger.info(type(row))
                    logger.info(row)
                    result += row.decode('utf-8')
            else:
                result = log.decode('utf-8')
        except docker.errors.NotFound:
            logger.info("Trying to get log from container '%s' that no longer exists." % container)
            result = "Countainer %s is no longer running." % container
    else:
        result = "Could not connect to docker host, no logs returned for %s." % container
    return result


# ----------------------------------------------------------------------
# SWARM STATISTICS COLLECTOR
# ----------------------------------------------------------------------

def collect_stats(url):
    global swarm, logger, refresh, timeout

    # start thread to collect services
    threads_stats['services'] = dict()
    thread = threading.Thread(target=collect_stats_services, args=[url])
    thread.daemon = True
    thread.start()
    logger.info("Start collecting services")

    # start thread to collect nodes
    threads_stats['nodes'] = dict()
    thread = threading.Thread(target=collect_stats_nodes, args=[url])
    thread.daemon = True
    thread.start()
    logger.info("Start collecting nodes")

    # start thread to compute stats
    threads_stats['compute'] = dict()
    thread = threading.Thread(target=collect_stats_compute)
    thread.daemon = True
    thread.start()
    logger.info("Start computing stats")


def collect_stats_services(url):
    global threads_stats, logger, lock, timeouts
    global swarm, services

    client = docker.DockerClient(base_url=url, version="auto", timeout=timeouts['docker'])
    while True:
        if 'services' not in threads_stats:
            break

        try:
            service_ids = list(services.keys())
            for service in client.services.list():
                if service.short_id not in services:
                    swarm['services'].append(service.short_id)
                    with lock:
                        services[service.short_id] = {
                            'name': service.name,
                            'replicas': {'requested': 0, 'running': 0},
                            'containers': list(),
                            'env': list(),
                            'nodes': list(),
                            'cores': 0,
                            'memory': 0,
                            'disk': {'used': 0, 'data': 0},
                        }
                        logger.info("Adding service %s [id=%s]" % (service.name, service.short_id))
                else:
                    service_ids.remove(service.short_id)
                services[service.short_id]['env'] = get_item(service.attrs, 'Spec.TaskTemplate.ContainerSpec.Env', list())
                v = get_item(service.attrs, 'Spec.Mode.Replicated.Replicas', 0)
                services[service.short_id]['replicas']['requested'] = v
            with lock:
                for key in service_ids:
                    service = services.pop(key, None)
                    if key in swarm['services']:
                        swarm['services'].remove(key)
                    if service:
                        logger.info("Removing service %s [id=%s]" % (service['name'], key))

            version['updated']['services'] = get_timestamp()
        except:
            logger.warning("Error collecting services.")
        time.sleep(timeouts['services'])


def collect_stats_nodes(url):
    global threads_stats, logger, lock, timeouts
    global swarm, nodes, docker_disk

    client = docker.DockerClient(base_url=url, version="auto", timeout=timeouts['docker'])
    while True:
        if 'nodes' not in threads_stats:
            break
        try:
            node_ids = list(nodes.keys())
            for node in client.nodes.list():
                attrs = node.attrs

                if node.short_id not in nodes:
                    description = attrs['Description']
                    resources = description['Resources']
                    cores = int(resources['NanoCPUs'] / 1000000000)
                    memory = resources['MemoryBytes']
                    disk = docker_disk
                    hostname = description['Hostname']
                    if 'Addr' in attrs['Status']:
                        if attrs['Status']['Addr'] == "127.0.0.1":
                            node_url = url
                        else:
                            node_url = 'tcp://%s:2375' % attrs['Status']['Addr']
                    else:
                        node_url = None

                    with lock:
                        nodes[node.short_id] = {
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

                if attrs['Spec']['Role'] == 'manager':
                    if node.short_id not in swarm['managers']:
                        swarm['managers'].append(node.short_id)
                oldstatus = None
                newstatus = attrs['Spec']['Availability']
                for k, v in swarm['nodes'].items():
                    if node.short_id in v:
                        oldstatus = k
                        break
                if newstatus != oldstatus:
                    nodes[node.short_id]['status'] = newstatus
                    if oldstatus:
                        swarm['nodes'][oldstatus].remove(node.short_id)
                    swarm['nodes'][newstatus].append(node.short_id)
                    if oldstatus == 'active':
                        swarm['cores']['total'] -= nodes[node.short_id]['cores']['total']
                        swarm['memory']['total'] -= nodes[node.short_id]['memory']['total']
                        swarm['disk']['available'] -= nodes[node.short_id]['disk']['available']

                        threads_stats.pop(node.short_id, None)
                        logger.info("Stopping collection node %s [id=%s]" % (nodes[node.short_id]['name'],
                                                                             node.short_id))

                    elif newstatus == 'active':
                        swarm['cores']['total'] += nodes[node.short_id]['cores']['total']
                        swarm['memory']['total'] += nodes[node.short_id]['memory']['total']
                        swarm['disk']['available'] += nodes[node.short_id]['disk']['available']

                        threads_stats[node.short_id] = dict()
                        thread = threading.Thread(target=collect_stats_node, args=[node.short_id,
                                                                                   nodes[node.short_id]['url']])
                        thread.daemon = True
                        thread.start()
                        logger.info("Starting collection node %s [id=%s]" % (nodes[node.short_id]['name'],
                                                                             node.short_id))

            with lock:
                for key in node_ids:
                    node = nodes.pop(key, None)
                    if node:
                        logger.info("Removing node %s [id=%s]" % (node['name'], key))

            version['updated']['nodes'] = get_timestamp()
        except:
            logger.warning("Error collecting nodes.")
        time.sleep(timeouts['nodes'])


def collect_stats_node(node_id, url):
    global threads_stats, logger, lock, timeouts
    global swarm, nodes, containers

    node = nodes[node_id]
    client = docker.DockerClient(base_url=url, version="auto", timeout=timeouts['docker'])
    next_full = time.time() + timeouts['node']
    while True:
        if node_id not in threads_stats:
            break
        try:
            if time.time() > next_full:
                next_full = time.time() + timeouts['node-full']
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
                if container_id not in swarm['containers']:
                    swarm['containers'].append(container_id)
                if container_id not in containers:
                    labels = container['Labels']
                    service_id = None
                    if 'com.docker.swarm.service.id' in labels and 'com.docker.swarm.service.name' in labels:
                        service_id = labels['com.docker.swarm.service.id'][:10]
                        services[service_id]['containers'].append(container_id)
                        services[service_id]['replicas']['running'] += 1
                        if node_id not in services[service_id]['nodes']:
                            services[service_id]['nodes'].append(node_id)
                        if service_id not in node['services']:
                            node['services'].append(service_id)
                    with lock:
                        containers[container_id] = {
                            'name': ",".join(container['Names']),
                            'state': None,
                            'status': container['Status'],
                            'env': list(),
                            'cores': 0,
                            'memory': 0,
                            'disk': {'used': 0, 'data': 0},
                            'service': service_id,
                            'node': node_id
                        }
                    logger.info("Adding container %s [id=%s] on node %s" % (",".join(container['Names']),
                                                                            container_id, node_id))

                c = containers[container_id]
                c['status'] = container['Status']
                c['env'] = get_item(container, 'Spec.TaskTemplate.ContainerSpec.Env', list())

                # update size stats
                if size:
                    # 'SizeRootFs' == size of all files
                    # 'SizeRw' == size of all files added to image
                    diff = container.get('SizeRootFs', 0) - c['disk']['used']
                    swarm['disk']['used'] += diff
                    node['disk']['used'] += diff
                    services[c['service']]['disk']['used'] += diff
                    c['disk']['used'] = container.get('SizeRootFs', 0)
                    diff = container.get('SizeRw', 0) - c['disk']['data']
                    swarm['disk']['data'] += diff
                    node['disk']['data'] += diff
                    services[c['service']]['disk']['data'] += diff
                    c['disk']['data'] = container.get('SizeRw', 0)

                # collect container stats if needed
                oldstate = c['state']
                newstate = container['State']
                if oldstate != newstate:
                    c['state'] = newstate
                    if oldstate == 'running':
                        swarm['containers'].append(container_id)
                        node['containers'].append(container_id)
                        threads_stats.pop(container_id, None)
                        logger.info("Stopping container collection %s [id=%s]" % (c['name'], container_id))
                    else:
                        swarm['containers'].remove(container_id)
                        node['containers'].remove(container_id)

                        threads_stats[container_id] = dict()
                        x = client.containers.get(container_id)
                        thread = threading.Thread(target=collect_stats_container, args=[x])
                        thread.daemon = True
                        thread.start()
                        logger.info("Starting container collection %s [id=%s]" % (c['name'], container_id))

            with lock:
                for key in container_ids:
                    container = containers.pop(key, None)
                    if key in node['containers']:
                        node['containers'].remove(key)
                    if key in swarm['containers']:
                        swarm['containers'].remove(key)
                    if container:
                        service_id = container['service']
                        services[service_id]['containers'].remove(key)
                        services[service_id]['replicas']['running'] -= 1
                        services[service_id]['nodes'].append(node_id)
                        node['services'].remove(service_id)
                        logger.info("Removing container %s [id=%s] on node %s" % (container['name'], key, node_id))

            node['updated'] = get_timestamp()
        except:
            logger.exception("Error collecting containers for node %s." % node_id)
        time.sleep(timeouts['node'])


def collect_stats_container(container):
    global containers, threads_stats, lock, logger

    mystats = threads_stats[container.short_id]
    c = containers[container.short_id]
    while True:
        if container.short_id not in threads_stats:
            break
        try:
            first_run = True
            generator = container.stats(decode=True, stream=True)
            for stats in generator:
                if container.short_id not in threads_stats:
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
            logger.info("Container is gone %s" % container.short_id)
            break
        except docker.errors.APIError as e:
            logger.info("Docker exception %s : %s" % (container.short_id, e.explanation))
        except:
            logger.exception("Error collecting stats for %s" % container.short_id)


def collect_stats_compute():
    global stats, swarm, services, nodes, containers, threads_stats, lock

    while True:
        if 'compute' not in threads_stats:
            break
        try:
            swarm_stats = {'cores': 0, 'memory': 0, 'disk': 0, 'data': 0}
            nodes_stats = {k: {'cores': 0, 'memory': 0, 'disk': 0, 'data': 0} for k in nodes.keys()}
            services_stats = {k: {'cores': 0, 'memory': 0, 'disk': 0, 'data': 0} for k in services.keys()}

            # compute cores/memory
            with lock:
                for k, v in containers.items():
                    if k in threads_stats:
                        s = threads_stats[k]
                        if s['cores']:
                            swarm_stats['cores'] += s['cores']
                            nodes_stats[v['node']]['cores'] += s['cores']
                            services_stats[v['service']]['cores'] += s['cores']
                        if s['memory']:
                            swarm_stats['memory'] += s['memory']
                            nodes_stats[v['node']]['memory'] += s['memory']
                            services_stats[v['service']]['memory'] += s['memory']
                    swarm_stats['disk'] += v['disk']['used']
                    swarm_stats['data'] += v['disk']['data']
                    nodes_stats[v['node']]['disk'] += v['disk']['used']
                    nodes_stats[v['node']]['data'] += v['disk']['data']
                    services_stats[v['service']]['disk'] += v['disk']['used']
                    services_stats[v['service']]['data'] += v['disk']['data']

            # swarm stats
            swarm['cores']['used'] = swarm_stats['cores']
            swarm['memory']['used'] = swarm_stats['memory']
            swarm['disk']['used'] = swarm_stats['disk']
            swarm['disk']['data'] = swarm_stats['data']
            deepcopy = copy.deepcopy(swarm)
            deepcopy.pop("managers")
            deepcopy['containers'] = len(deepcopy['containers'])
            deepcopy['services'] = len(deepcopy['services'])
            deepcopy['nodes'] = len(deepcopy['nodes']['active'])

            add_stats('swarm', deepcopy, '4hour')
            add_stats('swarm', deepcopy, '24hour')

            # node stats
            for k, v in nodes_stats.items():
                nodes[k]['cores']['used'] = v['cores']
                nodes[k]['memory']['used'] = v['memory']
                nodes[k]['disk']['used'] = v['disk']
                nodes[k]['disk']['data'] = v['data']

            # service stats
            for k, v in services_stats.items():
                services[k]['cores'] = v['cores']
                services[k]['memory'] = v['memory']
                services[k]['disk']['used'] = v['disk']
                services[k]['disk']['data'] = v['data']

            # save
            save_data()
        except:
            logger.exception("Error computing stats.")

        time.sleep(timeouts['stats'])


def add_stats(what, data, period):
    global stats

    now = datetime.datetime.utcnow()

    if period == '4hour':
        bin = now.replace(second=0, microsecond=0)
        delta = datetime.timedelta(hours=4)
    elif period == '24hour':
        bin = now.replace(minute=0, second=0, microsecond=0)
        delta = datetime.timedelta(hours=24)
    else:
        logger.warning("Could not compute stats for % for period=%s" % (what, period))
        return

    data = copy.deepcopy(data)

    if what not in stats:
        stats[what] = dict()
    if period not in stats[what]:
        stats[what][period] = list()

    data['time'] = bin.isoformat()
    data['_count'] = 1
    for x in stats[what][period]:
        if x['time'] == data['time']:
            average_stats(x, data, x['_count'])
            x['_count'] += 1
            break
    else:
        stats[what][period].append(data)

    while len(stats[what][period]) > 0:
        firstdate = dateutil.parser.parse(stats[what][period][0]['time'])
        if (bin - firstdate) < delta:
            break
        stats[what][period].pop(0)


def average_stats(cumalative, data, count):
    global logger

    for k, v in data.items():
        if k == '_count' or k == 'time':
            continue
        if k in cumalative:
            if isinstance(v, numbers.Number):
                try:
                    cumalative[k] = (cumalative[k] * count + v) / (count + 1)
                except:
                    logger.exception("Could not compute average for %s" % k)
            elif isinstance(v, dict):
                average_stats(cumalative[k], v, count)
            else:
                logger.debug("not a dict or number %s" % k)
                cumalative[k] = v
        else:
            cumalative[k] = v


# ----------------------------------------------------------------------
# LOAD/SAVE DATA
# ----------------------------------------------------------------------

def load_data():
    global logger, stats

    stats = dict()
    try:
        file = os.path.join(data_folder, 'stats.json')
        if os.path.isfile(file):
            stats = json.load(open(file, "rb"))
    except:
        logger.exception("Error reading stats.json")


def save_data():
    global data_folder, stats

    with open(os.path.join(data_folder, 'stats.json'), "w") as f:
        json.dump(stats, f)


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------

if __name__ == '__main__':
    main()
