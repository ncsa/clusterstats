#!/usr/bin/env python

"""Global variables and utility methods used across modules.

   Mainly config, logger, and a gethostipbyname method.
"""

# This file contains global variables.

# Use namedtuple in et_info_map to be able to access using attribute names such as et_info.def_service_name instead of et_info[0].
from collections import namedtuple
import os
import logging
# Used 'sys' to get the Python version.
import sys
# Used 'socket.gethostbyname_ex' for DNS name resolution.
import socket
# To escape characters such as '/' in the virtual host name and queue names.
import urllib

import swarmscale

# ====== Configuration File ======
# The module name is "configparser" for Python 3.x, "ConfigParser" for 2.x.
if sys.version_info[0] > 2:
    import configparser
    config = configparser.ConfigParser()
else:
    import ConfigParser
    config = ConfigParser.ConfigParser()

# Make the option name case sensitive.
config.optionxform = str

# Use an environment variable to support running multiple instances with one source tree.
config_file = os.getenv("SWARMSCALE_CONF", default='swarmscale.conf')

# ====== Logging ======
# Usage: 'env BD_LOG_LEVEL=DEBUG ./bdrabbitmq.py'
log_levels = {'notset'  : logging.NOTSET,   'NOTSET'  : logging.NOTSET,
              'debug'   : logging.DEBUG,    'DEBUG'   : logging.DEBUG,
              'info'    : logging.INFO,     'INFO'    : logging.INFO,
              'warn'    : logging.WARNING,  'WARN'    : logging.WARNING,
              'warning' : logging.WARNING,  'WARNING' : logging.WARNING,
              'error'   : logging.ERROR,    'ERROR'   : logging.ERROR,
              'critical': logging.CRITICAL, 'CRITICAL': logging.CRITICAL }
logging.basicConfig(level=logging.WARN,
                    format="%(asctime)-15s %(module)s %(levelname)-5s : %(message)s")

# ====== Utility Methods ======

def read_config():
    """Read the config file for some global variables."""
    config_file = 'swarm.conf.' + swarmscale.conf_extension
    global config, logger
    # To use the same config with updated config_file contents, need to first drop all existing content, then read again. Found no method to clear all contents, thus used remove_section().
    for section in config.sections():
        config.remove_section(section)
    config.read(config_file)
    app_name          = config.get('Logging', 'app_name')
    default_log_level = config.get('Logging', 'default_log_level')
    env_var_name      = config.get('Logging', 'env_var_name')
    logger = logging.getLogger(app_name)
    logger.setLevel(log_levels[os.getenv(env_var_name, default=default_log_level)])

    global elasticity_instance_name
    # Replace "-" with "_" to avoid problems. We use "-" to create VM names.
    elasticity_instance_name = config.get('bdmon', 'elasticity_instance_name').replace('-', '_')

    # Needed to pass RabbitMQ info to newly created VMs or Docker containers.
    # Used in OpenStack, Docker, RabbitMQ listener.
    read_rabbitmq_info()

    global unmanaged_hosts, unmanaged_IPs
    unmanaged_IPs = set()
    unmanaged_hosts = set(config.get('bdmon', 'unmanaged_hosts').split())
    for host in unmanaged_hosts:
        ip = gethostipbyname(host)
        if ip:
            unmanaged_IPs.add(gethostipbyname(host))

    Et_info = namedtuple('Et_info', ['def_service_name', 'min_num_instances', 'max_num_instances'])
    global et_info_map
    et_info_map = {}
    for (et_name, info_str) in config.items('Extractor Info'):
        # In CSV format: <extractor_type_name> = <default_service_name>, <minimum number of instances>, <maximum number of instances>.
        # Minimum must be an integer that's >= 0. Use '-' in the 'maximum...' field to indicate no limit. Must have 0 <= min <= max, otherwise the code exits.
        # In returned values, info[1] (min) is an integer, info[2] (max) is a string.
        info = map(lambda x: x.strip(), info_str.split(','))
        info[1] = int(info[1])
        if info[1] < 0:
            logger.error("Minimum number of instances for an extractor must be an integer that is >=0, not '" + info[1] + "'.")
            sys.exit(1)
        CHAR_NO_LIMIT = '-'
        # If max is not provided, set it to '-'.
        if len(info) < 3:
            info.append(CHAR_NO_LIMIT)
        elif info[2] != CHAR_NO_LIMIT:
            max_num = int(info[2])
            # Verify that min <= max.
            if info[1] > max_num:
                logger.error("Minimum number of instances for an extractor must be smaller than or equal to max, current min: '" + str(info[1]) + "', max: '" + info[2] + "'.")
                sys.exit(1)
        # Now uses _make() instead of the * operator Et_info(*info) to populate the named tuple, easier to understand.
        et_info_map[et_name] = Et_info._make(info)
    #logger.info("et_info_map: " + str(et_info_map))

    # Used to avoid putting a newly resumed/started Docker VM into the idle VM candidate list in scaling down.
    # Added here instead of in bdmon.py, because bdopenstack needs to update it when starting a VM, and it imports only bdglobals.
    global vm_last_activated_time_map
    vm_last_activated_time_map = {}

def gethostipbyname(hostname):
    """DNS name to IP resolution.

    Returns:
        The first non "127." IP returned by socket.gethostbyname_ex(),
        or None if the name can not be resolved by that method.
    """
    try:
        ips1 = socket.gethostbyname_ex(hostname)[2]
    except socket.gaierror as e:
        logger.error('DNS resolution error for host "' + hostname
                     + '": ' + str(e))
        return None
    else:
        ips2 = filter(lambda x: not x.startswith('127.'), ips1)
        return ips2[0]

def read_rabbitmq_info():
    # rabbitmq_uri is the access URI, containing username, password, extra conn parameters, while rabbitmq_vhost_uri is to identify the vhost and does not contain these items.
    global rabbitmq_uri, rabbitmq_exchange, rabbitmq_vhost_uri

    DEFAULT_AMQP_PORT = 5672
    host                = config.get('RabbitMQ', 'host')
    username            = config.get('RabbitMQ', 'username')
    password            = config.get('RabbitMQ', 'password')
    virtual_host        = config.get('RabbitMQ', 'virtual_host')
    rabbitmq_exchange   = config.get('RabbitMQ', 'exchange')
    extra_conn_params   = config.get('RabbitMQ', 'extra_conn_params')
    if virtual_host.isalnum():
        vhost_escaped   = virtual_host
    else: 
        # urllib.quote(string[,safe]). The optional safe param specifies addition characters that should not be quoted. Its default value is '/'.  Here use '' to force it to be escaped.
        vhost_escaped   = urllib.quote(virtual_host, '')
    if config.has_option('RabbitMQ', 'amqp_port'):
        amqp_port       = config.get('RabbitMQ', 'amqp_port')
    else:
        amqp_port       = str(DEFAULT_AMQP_PORT)

    rabbitmq_uri = 'amqp://' + username + ':' + password + '@' \
        + host + ':' + amqp_port + '/' + vhost_escaped + extra_conn_params
    rabbitmq_vhost_uri = 'amqp://%s:%s/%s' % (host, amqp_port, vhost_escaped)
    logger.debug("virtual_host: '" + virtual_host + "'")
    logger.debug("vhost_escaped: '" + vhost_escaped + "'")
    logger.debug("rabbitmq_uri: '" + rabbitmq_uri + "'")
    logger.debug("rabbitmq_vhost_uri: '" + rabbitmq_vhost_uri + "'")