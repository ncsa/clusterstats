#!/usr/bin/python -u

import getopt
import sys

import swarm
import rabbitmq

MAX_REPLICA = 5
sizing = 100
jitter = 20


def do_list(key, service_name, queues_mapping):
    service_metadata = swarm.get_service_info(service_name)
    if key in queues_mapping:
        queue_info = queues_mapping[key]
    else:
        print key, ' not found!'
        return
    (queuename, messages, consumers, msgs_ready) = queue_info
    replica = service_metadata['replicas']['requested']
    print '{:>20} {:>12} {:>12} {:>12} {:>12} {:>12}'.format(queuename, messages, consumers, msgs_ready, 'scale info',
                                                             replica)


def do_scale(key, service_name, queues_mapping):
    service_metadata = swarm.get_service_info(service_name)
    if key in queues_mapping:
        queue_info = queues_mapping[key]
    else:
        print key, ' not found!'
        return
    (queuename, messages, consumers, msgs_ready) = queue_info

    replica = service_metadata['replicas']['requested']
    if 0 != consumers:
        if 0 == replica:
            print '{:>20} {:>12} {:>12} {:>12} {:>12}'.format(queuename, messages, consumers, msgs_ready, 'scale up')
            swarm.scale_replica(service_name, 1)
        elif msgs_ready >= (replica * sizing + jitter) and MAX_REPLICA >= replica:
            # scale up
            print '{:>20} {:>12} {:>12} {:>12} {:>12}'.format(queuename, messages, consumers, msgs_ready, 'scale up')
            swarm.scale_replica(service_name, replica+1)
        elif msgs_ready < (replica * sizing - jitter) and 1 < replica:
            swarm.scale_replica(service_name, replica - 1)
            # scale down
            print '{:>20} {:>12} {:>12} {:>12} {:>12}'.format(queuename, messages, consumers, msgs_ready, 'scale down')
        else:
            print '{:>20} {:>12} {:>12} {:>12} {:>12} {:>12}'.format(queuename, messages, consumers, msgs_ready, 'no scale', replica)
    else:
        print queuename + " has 0 consumers"


Func = {'list': do_list, 'scale': do_scale}


def scale(env, type, op):
    swarm_mapping = swarm.get_swarm_namemapping(env, type)
    queues_mapping  = rabbitmq.get_queues_mapping(env, type)

    print '\t\t\t\t\t+++ ' + op + ' on ', env, ' ', type, ' +++'
    print '{:>20} {:>12} {:>12} {:>12} {:>12} {:>12}'.format('queuename', 'messages', 'consumers', 'msgs_ready', 'decision',
                                                             'replica')
    for key, service_name in swarm_mapping[env][type]:
        if op in Func:
            Func[op](key, service_name, queues_mapping)


def usage():
    print 'opts:'
    print '\t-l, list services information'
    print '\t-s, scale services\n'
    print 'args:'
    print '\t dts-dev or dap-dev or dts-prod or dap-prod\n'


def get_args(arg):
    names = arg.split('-')
    env_dict = {'dev': 'dev', 'prod': 'prod'}
    typ_dict = {'dts': 'extractor', 'dap': 'converter'}

    env = None
    type = None
    for name in names:
        if name in env_dict:
            env = name
        elif name in typ_dict:
            type = name
        else:
            sys.exit('unsupported args: ' + arg)

    if not env or not type:
        sys.exit('unsupported args: ' + arg)

    print op, env_dict.get(env), typ_dict.get(type)

    env = env_dict.get(env)
    type = typ_dict.get(type)
    return env, type

if __name__ == '__main__':
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'l:s', ['list', 'scale'])
    except getopt.GetoptError as err:
        sys.exit(err)

    if not opts:
        usage()
        sys.exit()

    for opt, arg in opts:
        if opt == '-l':
            op = 'list'
        elif opt == '-s':
            op = 'scale'
        else:
            usage()
            sys.exit()

    (env, type) = get_args(arg)

    scale(env, type, op)
