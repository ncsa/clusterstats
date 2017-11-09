#!/usr/bin/env python3

import argparse
import json
import logging
import logging.config
import os
import sys

import flask
import flask.ext
import flask_cors
from werkzeug.contrib.fixers import ProxyFix

import blueprint_api
import blueprint_html
import swarm
import utils

software_version = '1.0'


def main():
    # parse command line arguments
    parser = argparse.ArgumentParser(description='Extractor registration system.')
    parser.add_argument('--context', '-c', default=None,
                        help='application context (default=extractors)')
    parser.add_argument('--datadir', '-d', default=os.getenv("DATADIR", '.'),
                        help='location to store all data')
    parser.add_argument('--disk', default=30 * 1024 * 1024 * 1024,
                        help='disk space free on each docker node')
    parser.add_argument('--logging', '-l', default=os.getenv("LOGGER", None),
                        help='file or logging coonfiguration (default=None)')
    parser.add_argument('--port', '-p', type=int, default=9999,
                        help='port the server listens on (default=9999)')
    parser.add_argument('--swarm', '-s', default=os.getenv("SWARM", None),
                        help='swarm ipaddress:port')
    parser.add_argument('--timeout', '-t', default=5, type=int,
                        help='timeout for docker operations')
    parser.add_argument('--users', '-u', default=os.getenv("USERS", None),
                        help='users as json representation')
    parser.add_argument('--version', action='version', version='%(prog)s version=' + software_version)
    args = parser.parse_args()

    # setup logging
    config_logging(args.logging)
    logger = logging.getLogger(__name__)

    # set up collector
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
    swarm.initialize(swarm_url, folder=args.datadir, timeout=args.timeout, disksize=args.disk)

    # setup users
    if args.users and args.users != "":
        utils.users = json.loads(args.users)
    else:
        try:
            file = os.path.join(args.datadir, 'users.json')
            if os.path.isfile(file):
                utils.users = json.load(open(file, "rb"))
        except:  # pylint: disable=broad-except
            logger.exception("Error reading users.json")

    # setup app
    app = flask.Flask('swarmstats')
    app.wsgi_app = ProxyFix(app.wsgi_app)
    if args.context:
        context = args.context.rstrip('/')
        app.register_blueprint(blueprint_html.blueprint, url_prefix=context)
        app.register_blueprint(blueprint_api.blueprint, url_prefix=context + '/api')
    else:
        app.register_blueprint(blueprint_html.blueprint, url_prefix=None)
        app.register_blueprint(blueprint_api.blueprint, url_prefix='/api')

    # setup cors
    flask_cors.CORS(app)

    # start the app
    app.run(host="0.0.0.0", port=args.port, threaded=True)


# ----------------------------------------------------------------------
# HELPER FUNCTIONS
# ----------------------------------------------------------------------

def config_logging(config_info):
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
        logging.basicConfig(format='%(asctime)-15s %(levelname)-7s [%(threadName)-10s] : %(name)s - %(message)s',
                            level=logging.INFO)
        logging.getLogger(__name__).setLevel(logging.DEBUG)
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        logging.getLogger('swarm').setLevel(logging.DEBUG)


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------

if __name__ == '__main__':
    main()
