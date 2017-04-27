import os
import logging
# Used 'sys' to get the Python version.
import sys
import urllib

# ====== Configuration File ======
# The module name is "configparser" for Python 3.x, "ConfigParser" for 2.x.
if sys.version_info[0] > 2:
    import configparser
    config = configparser.ConfigParser()
else:
    import ConfigParser
    config = ConfigParser.ConfigParser()

class Config:
    DEFAULT_AMQP_PORT = 5672
    config_file = 'swarm.conf'
    rabbitmq_uri = ''
    rabbitmq_exchange = ''
    rabbitmq_vhost_uri = ''
    vhost_escaped = ''
    unmanaged_queues = ''
    username = ''
    password = ''
    host_url = ''

    swarm_username = ''
    swarm_password = ''
    swarm_base_url = ''
    swarm_http_host = ''

    def __init__(self, config_file_extension):
        self.config_file = self.config_file + config_file_extension
        config.read(self.config_file)
        self.read_swarm_info()
        self.read_rabbitmq_info()

    def read_swarm_info(self):
        self.swarm_username = config.get('Swarm', 'u')
        self.swarm_password = config.get('Swarm', 'p')
        self.swarm_base_url = config.get('Swarm', 'base_url')
        self.swarm_http_host = config.get('Swarm', 'swarm_http_host')

    def read_rabbitmq_info(self):
        host = config.get('RabbitMQ', 'host')
        self.username = config.get('RabbitMQ', 'username')
        self.password = config.get('RabbitMQ', 'password')
        virtual_host = config.get('RabbitMQ', 'virtual_host')
        self.rabbitmq_exchange = config.get('RabbitMQ', 'exchange')
        extra_conn_params = config.get('RabbitMQ', 'extra_conn_params')
        if virtual_host.isalnum():
            self.vhost_escaped = virtual_host
        else:
            # urllib.quote(string[,safe]). The optional safe param specifies addition characters that should not be quoted. Its default value is '/'.  Here use '' to force it to be escaped.
            self.vhost_escaped = urllib.quote(virtual_host, '')
        if config.has_option('RabbitMQ', 'amqp_port'):
            amqp_port = config.get('RabbitMQ', 'amqp_port')
        else:
            amqp_port = str(Config.DEFAULT_AMQP_PORT)

        self.rabbitmq_uri = 'amqp://' + self.username + ':' + self.password + '@' \
                       + host + ':' + amqp_port + '/' + self.vhost_escaped + extra_conn_params
        self.rabbitmq_vhost_uri = 'amqp://%s:%s/%s' % (host, amqp_port, self.vhost_escaped)

        management_protocol = config.get('RabbitMQ', 'management_protocol')
        host = config.get('RabbitMQ', 'host')
        management_port = config.get('RabbitMQ', 'management_port')
        self.virtual_host = config.get('RabbitMQ', 'virtual_host')

        self.host_url = management_protocol + '://' \
                   + host + ':' + management_port
        if virtual_host.isalnum():
            self.vhost_escaped = virtual_host
        else:
            # urllib.quote(string[,safe]). The optional safe param specifies addition characters that should not be quoted. Its default value is '/'.  Here use '' to force it to be escaped.
            self.vhost_escaped = urllib.quote(virtual_host, '')

        if config.has_option('bdmon', 'unmanaged_queues'):
            self.unmanaged_queues = set(config.get('bdmon', 'unmanaged_queues').split())
        else:
            self.unmanaged_queues = set()