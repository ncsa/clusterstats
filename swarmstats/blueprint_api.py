import copy
import os
import time

import flask

import server
import swarm
import utils

blueprint = flask.Blueprint('api',  __name__)

version = {
    'version': server.software_version,
    'build': os.getenv('BUILD', 'unknown'),
    'updates': {'services': None, 'nodes': None, 'containers': None}
}


# ----------------------------------------------------------------------
# VERSION API IMPLEMENTATION
# ----------------------------------------------------------------------

@blueprint.route('/version')
@utils.requires_user("admin", "viewer")
def api_version():
    version['updates'] = swarm.instance.updates
    return flask.jsonify(version)


# ----------------------------------------------------------------------
# SWARM API IMPLEMENTATION
# ----------------------------------------------------------------------

@blueprint.route('/swarm')
@utils.requires_user("admin", "viewer")
def api_swarm():
    if flask.request.args.get('full'):
        return flask.jsonify(swarm.instance.swarm)
    else:
        result = copy.deepcopy(swarm.instance.swarm)
        result['containers'] = len(result['containers'])
        result['services'] = len(result['services'])
        result['nodes'] = len(result['nodes']['active'])
        return flask.jsonify(result)


@blueprint.route('/swarm/stats', defaults={'period': None})
@blueprint.route('/swarm/stats/<period>')
@utils.requires_user("admin", "viewer")
def api_swarm_stats(period):
    return get_stats('swarm', period)


# ----------------------------------------------------------------------
# NODES API IMPLEMENTATION
# ----------------------------------------------------------------------

@blueprint.route('/nodes', defaults={'node': None})
@blueprint.route('/nodes/<node>')
@utils.requires_user("admin", "viewer")
def api_nodes(node):
    if node:
        (_, v) = utils.find_item(swarm.instance.nodes, node)
        if v:
            return flask.jsonify(v)
        else:
            return flask.Response('node "%s" not found' % node, status=404)
    else:
        if flask.request.args.get('full'):
            return flask.jsonify(swarm.instance.nodes)
        else:
            result = {k: v['name'] for k, v in swarm.instance.nodes.items()}
            return flask.jsonify(result)


@blueprint.route('/nodes/<node>/stats', defaults={'period': None})
@blueprint.route('/nodes/<node>/stats/<period>')
@utils.requires_user("admin", "viewer")
def api_nodes_stats(node, period):
    (k, _) = utils.find_item(swarm.instance.nodes, node)
    if k:
        return get_stats(k, period)
    else:
        return flask.Response('node "%s" not found' % node, status=404)


# ----------------------------------------------------------------------
# SERVICES API IMPLEMENTATION
# ----------------------------------------------------------------------

@blueprint.route('/services', defaults={'service': None})
@blueprint.route('/services/<service>')
@utils.requires_user("admin", "viewer")
def api_services(service=None):
    if service:
        (_, v) = utils.find_item(swarm.instance.services, service)
        if v:
            if flask.request.authorization.username == 'admin':
                return flask.jsonify(v)
            else:
                v = copy.copy(v)
                v.pop('env', None)
                return flask.jsonify(v)
        else:
            return flask.Response('service "%s" not found' % service, status=404)
    else:
        if flask.request.args.get('full'):
            if flask.request.authorization.username == 'admin':
                return flask.jsonify(swarm.instance.services)
            else:
                results = dict()
                for k, v in swarm.instance.services.items():
                    results[k] = copy.copy(v)
                    results[k].pop('env', None)
                return flask.jsonify(results)
        else:
            results = {k: v['name'] for k, v in swarm.instance.services.items()}
            return flask.jsonify(results)


@blueprint.route('/services/<service>/logs')
@utils.requires_user("admin", "viewer")
def api_services_logs(service):
    lines = int(flask.request.args.get('lines', '20'))
    if lines == 0:
        lines = 'all'
    log = swarm.instance.service_log(service, lines=lines)
    if log or log == '':
        return flask.Response(log, mimetype='text/ascii')
    else:
        return flask.Response('No logs found for %s' % service, status=404)


@blueprint.route('/services/<service>/restart', methods=['POST'])
@utils.requires_user("admin")
def api_services_restart(service):
    (k, v) = utils.find_item(swarm.instance.services, service)
    if k and v:
        replicas = v['replicas']['requested']
        api_services_scale(k, 0)
        time.sleep(30)
        api_services_scale(k, replicas)
        return flask.Response('service %s restarted' % service)
    else:
        return flask.Response('service "%s" not found' % service, status=404)


@blueprint.route('/services/<service>/scale/<count>', methods=['PUT'])
@utils.requires_user("admin")
def api_services_scale(service, count):
    (status, msg) = swarm.instance.services_scale(service, count)
    if status:
        return flask.Response('', status=204)
    else:
        return flask.Response(msg, status=404)


@blueprint.route('/services/<service>/stats', defaults={'period': None})
@blueprint.route('/services/<service>/stats/<period>')
@utils.requires_user("admin", "viewer")
def api_services_stats(service, period):
    (k, _) = utils.find_item(swarm.instance.services, service)
    if k:
        return get_stats(k, period)
    else:
        return flask.Response('service "%s" not found' % service, status=404)


# ----------------------------------------------------------------------
# CONTAINERS API IMPLEMENTATION
# ----------------------------------------------------------------------

@blueprint.route('/containers', defaults={'container': None})
@blueprint.route('/containers/<container>')
@utils.requires_user("admin", "viewer")
def api_containers(container=None):
    if container:
        (_, v) = utils.find_item(swarm.instance.containers, container)
        if v:
            if flask.request.authorization.username == 'admin':
                return flask.jsonify(v)
            else:
                v = copy.copy(v)
                v.pop('env', None)
                return flask.jsonify(v)
        else:
            return flask.Response('container "%s" not found' % container, status=404)
    else:
        if flask.request.args.get('full'):
            if flask.request.authorization.username == 'admin':
                return flask.jsonify(swarm.instance.containers)
            else:
                results = dict()
                for k, v in swarm.instance.containers.items():
                    results[k] = copy.copy(v)
                    results[k].pop('env', None)
                return flask.jsonify(results)
        else:
            results = {k: v['name'] for k, v in swarm.instance.containers.items()}
            return flask.jsonify(results)


@blueprint.route('/containers/<container>/logs')
@utils.requires_user("admin", "viewer")
def api_containers_logs(container):
    lines = int(flask.request.args.get('lines', '20'))
    if lines == 0:
        lines = 'all'
    log = swarm.instance.log_container(container, lines=lines)
    if log or log == '':
        return flask.Response(log, mimetype='text/ascii')
    else:
        return flask.Response('No logs found for %s' % container, status=404)


@blueprint.route('/containers/<container>/stats', defaults={'period': None})
@blueprint.route('/containers/<container>/stats/<period>')
@utils.requires_user("admin", "viewer")
def api_containers_stats(container, period):
    (k, _) = utils.find_item(swarm.instance.containers, container)
    if k:
        return get_stats(k, period)
    else:
        return flask.Response('container "%s" not found' % container, status=404)


# ----------------------------------------------------------------------
# LOG COLLECTOR
# ----------------------------------------------------------------------

def get_stats(what, period):
    """
    From the stats return the stats for the right period. If no period is given it will retunr
    a list of the periods.
    :param what: the stats to return, swar, container id, service id, etc.
    :param period: period of stats to return 4hour, ...
    :return: stats for that period, or list of periods
    """

    if what in swarm.instance.stats:
        if not period:
            return flask.jsonify(list(swarm.instance.stats[what].keys()))
        elif period in swarm.instance.stats[what]:
            return flask.jsonify(swarm.instance.stats[what][period])
        else:
            return flask.Response('no stats found for %s in %s' % (period, what), status=404)
    else:
        return flask.Response('no stats found for %s' % what, status=404)
