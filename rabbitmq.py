#!/usr/bin/env python

"""To get info from RabbitMQ regarding the queues, extractors, channels etc."""
import json
import requests
import string
import datetime
# socket.inet_aton is used to sort IP addresses.
from socket import inet_aton
# 'subprocess32' is used to execute a script to get the current NAT mapping.
import subprocess32
# urllib is used to escape characters such as '/' in the virtual host name and queue names.
import urllib
import utilities
import Config


class JSONObject:
    def __init__(self, d):
        self.__dict__ = d


def get_json_data(url):
    r = requests.get(config.host_url + url, auth=(config.username, config.password))
    r.raise_for_status()
    reply = r.text
    data = json.loads(reply, object_hook=JSONObject)
    return data


def get_queues():
    '''Get info of all managed queues in RabbitMQ.

    Returns:
        A map from queue name to a tuple: (num_messages, num_consumers).
    '''
    # Changed to a local variable from global.
    bd_qs = {}

    url = '/api/queues/' + config.vhost_escaped
    data = get_json_data(url)
    for x in data:
        # x has the following info:
        #     name, messages, messages_ready, messages_unacknowledged,
        #     consumers, idle_since,
        #     and if non-zero, message_stats.publish, message_stats.deliver (all-time total number)
        # Also skip the 'amq.gen-*' queues that Medici uses to receive extraction status.
        num_msgs_published = 0
        num_msgs_delivered = 0
        #print x.name
        if not x.name.startswith('error') and not x.name.startswith('amq'):
            if hasattr(x, 'consumers') and hasattr(x, 'messages_ready'):
                key = string.replace(x.name, '.', '')
                key = string.replace(key, '_', '')
                key = string.replace(key, '-', '')
                bd_qs[key] = (x.name, x.messages, x.consumers, x.messages_ready)
            else:
                print x.name, " not have consumers or messages_ready"
    return bd_qs


def get_queues_mapping(env, type):
    config_file_extension = '.' + type + '-' + env
    global config
    config = Config.Config(config_file_extension)
    in_queues = get_queues()
    return in_queues
    

if __name__ == '__main__':
    env = 'dev'
    type = 'extractor'
    get_queues_mapping(env, type)

