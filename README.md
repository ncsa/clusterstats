To create a cluster run:
  ./cluster.sh

This assumes you have installed the openstack python package as well as loaded the appropriate openstack rc file.
WORKERS=20 : the number of workers, master will not be a worker node

To create a service:
```
docker service create \
  --name dev-converter-OpenJPEG \
  --network elasticity \
  --env "RABBITMQ_URI=amqp://username:password@rabbitmq.ncsa.illinois.edu:5672/dap-dev" \
  --mode replicated \
  --replicas 2 \
  ncsapolyglot/converters-openjpeg
```

The name should be of the following syntax (queue name should replace . with _):
(dev|prod)-(converter|extractor)-<queue_name>

To create the swarmstats container:
```
docker -H ${CLUSTER} service create \
  --name status \
  --publish 9999:9999 \
  --mount 'type=bind,src=/home/core,dst=/data' \
  --constraint 'node.hostname == bd-swarm-worker-06.os.ncsa.edu' \
  kooper/swarmstats python ./server.py --swarm ${CLUSTER}
```

The swarmstats writes the stats to /home/core/*.json so it can be restarted and keep history. This is also the
reason why the container is constraint to run on bd-swarm-sword-06.


To run swarmscale container:
```
docker run --rm -it --publish 7777:7777 -e 'TZ=/usr/share/zoneinfo/US/Central' -e "MONGO_URL=mongodb://mongohostname:port" -e "SWARM_URL=http://username:passwd@swarmhostname:port" -e "Rabbitmq_URLS={'swarm-prefix1' : 'amqp://username:passwd@host:port/vhost1', 'swarm-prefix2' : 'amqp://username:passwd@host:port/vhost2'}" --name swarmscale bingzhang/swarmscale
```
