import flask

import utils
import swarm

blueprint = flask.Blueprint('html',  __name__, static_folder='static', template_folder='templates')


@blueprint.route('/', defaults={'page': 'dashboard'})
@blueprint.route('/<page>')
@utils.requires_user("admin", "viewer")
def html_page(page):
    """
    Return any static page with .html appended.
    """
    return blueprint.send_static_file('%s.html' % page)


@blueprint.route('/services/<service>/logs')
@utils.requires_user("admin", "viewer")
def html_services_logs(service):
    """
    Return log viewer for a specific service.
    """
    (k, v) = utils.find_item(swarm.instance.services, service)
    return flask.render_template('logs.html', service_id=k, service_name=v['name'], containers=v['containers'])


@blueprint.route('/swagger')
def html_swagger():
    """
    Return swagger documentation
    """
    return blueprint.send_static_file('swagger.yml')
