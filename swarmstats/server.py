#!/usr/bin/env python3

import argparse
import copy
import datetime
import inspect
import json
import logging
import logging.config
import os
import sys
import threading
import time
import urllib

import dateutil.parser
import docker
import flask
import flask.ext
import flask_basicauth
import flask_cors
from werkzeug.contrib.fixers import ProxyFix

software_version = '1.0'

logger = None
app = None
swarm_url = None
node_url = None
threads_stats = dict()
lock = threading.Lock()
context = '/'
data_folder = '.'
refresh = 60
timeout = 5

version = {'version': software_version, 'build': os.getenv('BUILD', 'unknown'), 'updated': 'not yet'}
stats = dict()
swarm = dict()
services = dict()
nodes = dict()
containers = dict()

bp_api = flask.Blueprint('api',  __name__)
bp_html = flask.Blueprint('html',  __name__, static_folder='static')


def main():
    global logger, data_folder, app, swarm_url, node_url, refresh

    # parse command line arguments
    parser = argparse.ArgumentParser(description='Extractor registration system.')
    parser.add_argument('--context', '-c', default=None,
                        help='application context (default=extractors)')
    parser.add_argument('--datadir', '-d', default=os.getenv("DATADIR", '.'),
                        help='location to store all data')
    parser.add_argument('--layout', action='store_true',
                        help='do not collect statistics.')
    parser.add_argument('--logging', '-l', default=os.getenv("LOGGER", None),
                        help='file or logging coonfiguration (default=None)')
    parser.add_argument('--node', '-n', default=os.getenv("NODE", None),
                        help='node ipaddress:port')
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
    if not args.layout:
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
        elif args.node and args.node != "":
            if args.node.startswith('unix://'):
                node_url = args.node
            elif args.node.startswith('tcp://'):
                node_url = args.node
            elif ':' in args.node:
                node_url = 'tcp://' + args.node
            else:
                node_url = 'tcp://' + args.node + ':2375'
        else:
            logger.error("No swarm or node specified")
            parser.print_help()
            sys.exit(-1)
        thread = threading.Thread(target=stats_thread)
        thread.daemon = True
        thread.start()

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

    # setup basic auth
    username = 'swarmstats'
    if os.path.isfile('/run/secrets/username'):
        with open('/run/secrets/username', 'r') as secret:
            username = secret.readline()
    password = 'browndog'
    if os.path.isfile('/run/secrets/password'):
        with open('/run/secrets/password', 'r') as secret:
            password = secret.readline()
    app.config['BASIC_AUTH_USERNAME'] = username
    app.config['BASIC_AUTH_PASSWORD'] = password
    app.config['BASIC_AUTH_FORCE'] = True
    flask_basicauth.BasicAuth(app)

    # start the app
    app.run(host="0.0.0.0", port=args.port)


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
    else:
        for k, v in where.items():
            if v['name'] == id:
                return (k, v)
    return (None, None)


# ----------------------------------------------------------------------
# HTML PAGES
# ----------------------------------------------------------------------

@bp_html.route('/', defaults={'page': 'dashboard'})
@bp_html.route('/<page>')
def html_static(page):
    global app
    return app.send_static_file('%s.html' % page)


# ----------------------------------------------------------------------
# VERSION API IMPLEMENTATION
# ----------------------------------------------------------------------

@bp_api.route('/version')
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
def api_swarm():
    global swarm
    return flask.jsonify(swarm)


@bp_api.route('/swarm/stats', defaults={'period': None})
@bp_api.route('/swarm/stats/<period>')
def api_swarm_stats(period):
    return get_stats('swarm', period)


# ----------------------------------------------------------------------
# NODES API IMPLEMENTATION
# ----------------------------------------------------------------------

@bp_api.route('/nodes', defaults={'node': None})
@bp_api.route('/nodes/<node>')
def api_nodes(node):
    global nodes

    if node:
        result = nodes.get(node, None)
        if not result:
            for x in nodes.values():
                if x['name'] == node:
                    result = x
                    break
        if result:
            return flask.jsonify(result)
        else:
            return flask.Response('Node "%s" not found' % node, status=404)
    else:
        result = {k: v['name'] for k, v in nodes.items()}
        return flask.jsonify(result)


@bp_api.route('/nodes/<node>/stats', defaults={'period': None})
@bp_api.route('/nodes/<node>/stats/<period>')
def api_nodes_stats(node, period):
    global nodes

    key = None
    if node in nodes:
        key = node
    else:
        for k, v in nodes.items():
            if v['name'] == node:
                key = k
                break
    if key:
        return get_stats(key, period)
    else:
        return flask.Response('Node "%s" not found' % node, status=404)


# ----------------------------------------------------------------------
# SERVICES API IMPLEMENTATION
# ----------------------------------------------------------------------

@bp_api.route('/services', defaults={'service': None})
@bp_api.route('/services/<service>')
def api_services(service=None):
    global services

    if service:
        result = services.get(service, None)
        if not result:
            for x in services.values():
                if x['name'] == service:
                    result = x
                    break
        if result:
            return flask.jsonify(result)
        else:
            return flask.Response('Service "%s" not found' % service, status=404)
    else:
        #result = {k: v['name'] for k, v in services.items()}
        return flask.jsonify(services)


@bp_api.route('/services/<service>/logs')
def api_services_logs(service):
    global services, swarm_url

    lines = int(flask.request.args.get('lines', '20'))
    if lines == 0:
        lines = 'all'
    log = service_log(service, lines=lines)
    if log or log == '':
        return flask.Response(log, mimetype='text/ascii')
    else:
        return flask.Response('No logs found for %s' % service, status=404)


@bp_api.route('/services/<service>/stats', defaults={'period': None})
@bp_api.route('/services/<service>/stats/<period>')
def api_services_stats(service, period):
    global services

    key = None
    if service in services:
        key = service
    else:
        for k, v in services.items():
            if v['name'] == service:
                key = k
                break
    if key:
        return get_stats(key, period)
    else:
        return flask.Response('service "%s" not found' % service, status=404)


# ----------------------------------------------------------------------
# CONTAINERS API IMPLEMENTATION
# ----------------------------------------------------------------------

@bp_api.route('/containers', defaults={'container': None})
@bp_api.route('/containers/<container>')
def api_containers(container=None):
    global containers

    if container:
        result = containers.get(container, None)
        if not result:
            for x in containers.values():
                if x['name'] == container:
                    result = x
                    break
        if result:
            return flask.jsonify(result)
        else:
            return flask.Response('container "%s" not found' % container, status=404)
    else:
        result = {k: v['name'] for k, v in containers.items()}
        return flask.jsonify(result)


@bp_api.route('/containers/<container>/logs')
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
def api_containers_stats(container, period):
    global containers

    key = None
    if container in containers:
        key = container
    else:
        for k, v in containers.items():
            if v['name'] == container:
                key = k
                break
    if key:
        return get_stats(key, period)
    else:
        return flask.Response('container "%s" not found' % container, status=404)


# ----------------------------------------------------------------------
# LOG COLLECTOR
# ----------------------------------------------------------------------

def service_log(service, lines=10):
    global services, nodes, containers

    s = services.get(service, None)
    if not s and len(service) > 10:
        s = services.get(service[:10], None)
    if not s:
        for v in services.values():
            if v['name'] == service:
                s = v
                break
    if not s:
        return None

    log = ""
    for c in s['containers']:
        log += container_log(c, lines, True)
    sorted_logs = sorted(log.split("\n"))
    log = ""
    if lines != 'all':
        sorted_logs = sorted_logs[-lines:]
    for line in sorted_logs:
        pieces = line.split(maxsplit=1)
        if len(pieces) == 2:
            log += pieces[1] + "\n"

    return log


def container_log(container, lines=10, timestamps=False):
    global nodes, containers

    key = None
    if container in containers:
        key = container
    if not key and len(container) > 10:
        if container[:10] in containers:
            key = container[:10]
    if not key:
        for k, v in containers.items():
            if v['name'] == container:
                key = k
                break
        else:
            key = None
    if not key:
        return None

    node = nodes[containers[key]['node']]
    if 'url' in node:
        url = node['url']
    elif 'addr' in node:
        url = 'tcp://' + node['addr'] + ':2375'
    else:
        url = None

    if url:
        result = ""
        client = docker.APIClient(base_url=url, version="auto", timeout=timeout)
        log = client.logs(key, stdout=True, stderr=True, follow=False, timestamps=timestamps, tail=lines)
        if inspect.isgenerator(log):
            for row in log:
                logger.info(type(row))
                logger.info(row)
                result += row.decode('utf-8')
        else:
            result = log.decode('utf-8')
    else:
        result = "Could not connect to docker host, no logs returned for %s." % container
    return result


# ----------------------------------------------------------------------
# SWARM STATISTICS COLLECTOR
# ----------------------------------------------------------------------

def stats_thread():
    global logger, swarm_url, node_url, refresh, timeout

    while True:
        start = datetime.datetime.utcnow()
        try:
            if swarm_url:
                (swarm, services, nodes, containers) = collect_stats_swarm(swarm_url)
            else:
                (swarm, services, nodes, containers) = collect_stats_node(node_url)
            compute_stats(swarm, services, nodes, containers)
            version['time'] = (datetime.datetime.utcnow() - start).total_seconds()
        except:
            logger.exception("Error collecting stats.")
        elapsed = (datetime.datetime.utcnow() - start).total_seconds()
        version['time'] = elapsed
        if elapsed < refresh:
            time.sleep(refresh - elapsed)


def collect_stats_swarm(url):
    global threads_stats, timeout

    client = docker.DockerClient(base_url=url, version="auto", timeout=timeout)

    swarm = {
        'cores': {'total': 0, 'used': 0},
        'memory': {'total': 0, 'used': 0},
        'disk': {'available': 0, 'used': 0, 'data': 0},
        'managers': list(),
        'nodes': 0,
        'services': 0,
        'containers': 0
    }
    services = dict()
    nodes = dict()
    containers = dict()

    # collect services
    for service in client.services.list():
        swarm['services'] += 1

        attrs = service.attrs
        services[service.short_id] = {
            'name': service.name,
            'replicas': 0,
            'containers': list(),
            'nodes': list(),
            'cores': 0,
            'memory': 0,
            'disk': {'used': 0, 'data': 0},
        }

    # collect nodes
    for node in client.nodes.list():
        attrs = node.attrs
        # node information
        description = attrs['Description']
        hostname = description['Hostname']
        resources = description['Resources']
        cores = int(resources['NanoCPUs'] / 1000000000)
        memory = resources['MemoryBytes']
        # TODO hack, assumption is each node has 40GB storage
        disk = 30 * 1024 * 1024 * 1024
        nodes[node.short_id] = {
            'name': hostname,
            'addr': attrs['Status'].get('Addr', None),
            'cores': {'total': cores, 'used': 0},
            'memory': {'total': memory, 'used': 0},
            'disk': {'available': disk, 'used': 0, 'data': 0},
            'status': attrs['Spec']['Availability'],
            'services': list(),
            'containers': list()
        }

        swarm['nodes'] += 1
        if attrs['Spec']['Role'] == 'manager':
            swarm['managers'].append(node.short_id)
        if attrs['Spec']['Availability'] == 'active':
            swarm['cores']['total'] += cores
            swarm['memory']['total'] += memory
            swarm['disk']['available'] += disk

        # container information
        if 'Addr' in attrs['Status']:
            url = 'tcp://%s:2375' % attrs['Status']['Addr']
            worker = docker.DockerClient(base_url=url)
            for c in worker.api.containers(size=True):
                container = worker.containers.get(c['Id'])

                attrs = container.attrs
                config = attrs['Config']
                labels = config['Labels']
                # 'SizeRootFs' == size of all files
                # 'SizeRw' == size of all files added to image
                containers[container.short_id] = {
                    'name': container.name,
                    'status': container.status,
                    'cores': 0,
                    'memory': 0,
                    'disk': {'used': c.get('SizeRootFs', 0), 'data': c.get('SizeRw', 0)},
                    'service': dict(),
                    'node': node.short_id
                }

                swarm['containers'] += 1
                swarm['disk']['used'] += c.get('SizeRootFs', 0)
                swarm['disk']['data'] += c.get('SizeRw', 0)

                nodes[node.short_id]['containers'].append(container.short_id)
                nodes[node.short_id]['disk']['used'] += c.get('SizeRootFs', 0)
                nodes[node.short_id]['disk']['data'] += c.get('SizeRw', 0)
                nodes[node.short_id]['containers'].append(container.short_id)

                if 'com.docker.swarm.service.id' in labels and 'com.docker.swarm.service.name' in labels:
                    service_id = labels['com.docker.swarm.service.id'][:10]
                    containers[container.short_id]['service'] = service_id
                    services[service_id]['containers'].append(container.short_id)
                    services[service_id]['replicas'] += 1
                    services[service_id]['disk']['used'] += c.get('SizeRootFs', 0)
                    services[service_id]['disk']['data'] += c.get('SizeRw', 0)
                    if node.short_id not in services[service_id]['nodes']:
                        services[service_id]['nodes'].append(node.short_id)
                    if service_id not in nodes[node.short_id]['services']:
                        nodes[node.short_id]['services'].append(service_id)

                with lock:
                    if container.short_id not in threads_stats:
                        thread = threading.Thread(target=container_stats, args=[container])
                        thread.daemon = True
                        thread.start()
                        threads_stats[container.short_id] = dict()
                        logger.info("Start collecting stats for %s" % container.short_id)

    return (swarm, services, nodes, containers)


def collect_stats_node(url):
    global threads_stats, timeout, lock

    services = dict()
    nodes = dict()
    containers = dict()

    client = docker.DockerClient(base_url=url, version="auto", timeout=timeout)
    attrs = client.info()

    cores = attrs['NCPU']
    memory = attrs['MemTotal']

    swarm = {
        'cores': {'total': cores, 'used': 0},
        'memory': {'total': memory, 'used': 0},
        'nodes': 1,
        'services': 0,
        'containers': 0
    }

    nodes['0'] = {
        'name': attrs['Name'],
        'url': url,
        'cores': {'total': cores, 'used': 0},
        'memory': {'total': memory, 'used': 0},
        'services': list(),
        'containers': list()
    }

    for container in client.containers.list():
        swarm['containers'] += 1

        attrs = container.attrs
        config = attrs['Config']
        labels = config['Labels']
        containers[container.short_id] = {
            'name': container.name,
            'status': container.status,
            'cores': 0,
            'memory': 0,
            'service': dict(),
            'node': '0'
        }
        nodes['0']['containers'].append(container.short_id)
        if 'com.docker.swarm.service.id' in labels and 'com.docker.swarm.service.name' in labels:
            service_id = labels['com.docker.swarm.service.id'][:10]
            containers[container.short_id]['service'] = service_id
            services[service_id]['containers'].append(container.short_id)
            services[service_id]['replicas'] += 1
            if '0' not in services[service_id]['nodes']:
                services[service_id]['nodes'].append('0')
            if service_id not in nodes['0']['services']:
                nodes['0']['services'].append(service_id)

        with lock:
            if container.short_id not in threads_stats:
                thread = threading.Thread(target=container_stats, args=[container])
                thread.daemon = True
                thread.start()
                threads_stats[container.short_id] = dict()
                logger.info("Start collecting stats for %s" % container.short_id)

    return (swarm, services, nodes, containers)


def container_stats(container):
    global containers, threads_stats, lock

    generator = container.stats(decode=True, stream=True)
    for stats in generator:
        if container.short_id not in threads_stats:
            break
        cpu_percent = 0.0
        cpu_stats = stats['cpu_stats']
        precpu_stats = stats['precpu_stats']
        memory = int(stats['memory_stats'].get('usage', "0"))
        if 'system_cpu_usage' in precpu_stats:
            system_delta = float(cpu_stats['system_cpu_usage']) - float(precpu_stats['system_cpu_usage'])
            cpu_delta = float(cpu_stats['cpu_usage']['total_usage']) - float(precpu_stats['cpu_usage']['total_usage'])
            if system_delta > 0.0 and cpu_delta > 0.0:
                cpu_percent = round((cpu_delta / system_delta) * float(len(cpu_stats['cpu_usage']['percpu_usage'])), 2)
        threads_stats[container.short_id] = {'cores': cpu_percent, 'memory': memory}
    with lock:
        del threads_stats[container.short_id]
    logger.info("Done collecting stats for %s" % container.short_id)


def compute_stats(new_swarm, new_services, new_nodes, new_containers):
    global version, stats, swarm, services, nodes, containers, threads_stats, lock

    if version['updated'] != 'not yet':
        # compute statistics
        with lock:
            for key, value in threads_stats.items():
                if key in new_containers:
                    container = new_containers[key]
                    if 'cores' in value:
                        new_swarm['cores']['used'] += value['cores']
                        container['cores'] = value['cores']
                        new_services[container['service']]['cores'] += value['cores']
                        new_nodes[container['node']]['cores']['used'] += value['cores']
                    if 'memory' in value:
                        new_swarm['memory']['used'] += value['memory']
                        container['memory'] = value['memory']
                        new_services[container['service']]['memory'] += value['memory']
                        new_nodes[container['node']]['memory']['used'] += value['memory']

        # store stats
        now = datetime.datetime.utcnow()
        if 'swarm' not in stats:
            stats['swarm'] = dict()
        if '4hour' not in stats['swarm']:
            stats['swarm']['4hour'] = list()
        deepcopy = copy.deepcopy(new_swarm)
        deepcopy.pop("managers")
        deepcopy['time'] = now.isoformat()
        stats['swarm']['4hour'].append(deepcopy)

        delta = datetime.timedelta(hours=4)
        while len(stats['swarm']['4hour']) > 0:
            firstdate = dateutil.parser.parse(stats['swarm']['4hour'][0]['time'])
            if (now - firstdate) < delta:
                break
            stats['swarm']['4hour'].pop(0)

        # overwrite old values
        swarm = new_swarm
        services = new_services
        nodes = new_nodes
        containers = new_containers
        save_data()

    # save new information
    version['updated'] = datetime.datetime.utcnow().isoformat(timespec='seconds') + "Z"


# ----------------------------------------------------------------------
# LOAD/SAVE DATA
# ----------------------------------------------------------------------

def load_data():
    global logger, stats, swarm, services, nodes, containers

    stats = load_json_data('stats')
    swarm = load_json_data('swarm')
    services = load_json_data('services')
    nodes = load_json_data('nodes')
    containers = load_json_data('containers')


def load_json_data(filename):
    global logger, data_folder
    try:
        file = os.path.join(data_folder, '%s.json' % filename)
        if os.path.isfile(file):
            return json.load(open(file, "rb"))
    except:
        logger.exception("Error reading %s.json" % filename)
    return dict()


def save_data():
    global data_folder, stats, swarm, services, nodes, containers

    with open(os.path.join(data_folder, 'stats.json'), "w") as f:
        json.dump(stats, f)
    with open(os.path.join(data_folder, 'swarm.json'), "w") as f:
        json.dump(swarm, f)
    with open(os.path.join(data_folder, 'services.json'), "w") as f:
        json.dump(services, f)
    with open(os.path.join(data_folder, 'nodes.json'), "w") as f:
        json.dump(nodes, f)
    with open(os.path.join(data_folder, 'containers.json'), "w") as f:
        json.dump(containers, f)


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------

if __name__ == '__main__':
    main()
