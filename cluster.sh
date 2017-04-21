#!/bin/bash

# TODO add TLS security

CLUSTER="bd-swarm"
FLAVOR="m1.medium"
KEY="kooper"
IPADDR=""
# stable beta alpha
RELEASE="alpha"
SECURITY="docker"

WORKERS=20
WAIT_WORKER="NO"

echo "CLUSTER       : ${CLUSTER}"
echo "WORKERS       : ${WORKERS}"
echo "SECURITY      : ${SECURITY}"

# make sure security group exists
SECURITY_ID=$( openstack security group list | awk "/ ${SECURITY} / { print \$2 }" )
if [ "$SECURITY_ID" == "" ]; then
    echo "Create security group. Make sure you open all ports for both TCP and UDP to local network."
    echo "Make sure port 2375 and 2376 are closed to the outside, e.g. :"
    echo "Ingress IPv4  ICMP   Any         0.0.0.0/0"
    echo "Ingress IPv4  TCP      1 - 65535 192.168.5.0/24"
    echo "Ingress IPv4  UDP      1 - 65535 192.168.5.0/24"
    echo "Ingress IPv4  TCP      1 - 65535 141.142.0.0/16"
    echo "Ingress IPv4  TCP      1 -  2374 0.0.0.0/0"
    echo "Ingress IPv4  TCP   2377 - 65535 0.0.0.0/0"
    exit -1
fi

# check for network magic
if [ "${OS_PROJECT_NAME}" == "BROWNDOG" ]; then
    NETWORK_ID=$( openstack network list | awk "/ BROWNDOG-net / { print \$2 }" )
    NET_ID="--nic net-id=${NETWORK_ID}"
else
    NET_ID=""
fi

# get IP address
if [ -z "${IPADDR}" ]; then
    IPADDR=$( awk "/^${CLUSTER}-master	/ { print \$2 }" ipaddress.txt )
    if [ -z "${IPADDR}" ]; then
        IPADDR=$( openstack floating ip create ext-net | awk "/^ | floating_ip_address / { print \$4 }" )
        echo "${CLUSTER}-master	$IPADDR" >> ipaddress.txt
    fi
fi
echo "IPADDR        : ${IPADDR}"

# find latest coreos image
IMAGE_ID=$( openstack image list | awk "/ CoreOS ${RELEASE} / { print \$2 }" | head -1 )
if [ "$IMAGE_ID" == "" ]; then
    # create coreos image
    rm -f coreos_production_openstack_image.img.bz2 coreos_production_openstack_image.img
    wget https://${RELEASE}.release.core-os.net/amd64-usr/current/coreos_production_openstack_image.img.bz2
    bunzip2 coreos_production_openstack_image.img.bz2
    openstack image create --container-format bare --disk-format qcow2  --file coreos_production_openstack_image.img "CoreOS ${RELEASE}"
    rm -f coreos_production_openstack_image.img.bz2 coreos_production_openstack_image.img
    IMAGE_ID=$( openstack image list | awk "/ CoreOS ${RELEASE} / { print \$2 }" | head -1 )
fi
echo "CoreOS        : ${RELEASE} = ${IMAGE_ID}"

case $RELEASE in
  "stable")
      OPTS=""
      ;;
  "beta")
      OPTS=""
      ;;
  "alpha")
      OPTS="--experimental"
      ;;
esac

# create clients
cat > /tmp/cluster-manager.sh << EOF
#cloud-config

coreos:
  units:
    - name: docker.service
      command: start
      enable: true
      drop-ins:
        - name: 10-docker-opts.conf
          content: |
            [Service]
            Environment="DOCKER_OPTS=${OPTS} -H tcp://0.0.0.0:2375"
    - name: docker-swarm-join.service
      command: start
      content: |
        [Unit]
        Description=Inits a swarm

        [Service]
        Type=oneshot
        ExecStart=/bin/sh -c "docker swarm init"

EOF

# create swarm master
INSTANCE_ID=$( openstack server list | awk "/ ${CLUSTER}-master / { print \$2 }" )
if [ -z "${INSTANCE_ID}" ]; then
    INSTANCE_ID=$( openstack server create ${NET_ID} --flavor ${FLAVOR} --key-name ${KEY} --security-group "${SECURITY}" --image ${IMAGE_ID} --user-data /tmp/cluster-manager.sh ${CLUSTER}-master | awk "/^ | id / { print \$4 }" )
fi
echo "INSTANCE      : ${INSTANCE_ID}"
echo "URL           : https://nebula.ncsa.illinois.edu/dashboard/project/instances/${INSTANCE_ID}"
READY=""
while [ "${READY}" != "ACTIVE" ]; do
    READY=$( openstack server show -c status ${INSTANCE_ID} | awk '/ status / { print $4}' )
    if [ "${READY}" == "ERROR" ]; then
        exit -1
    fi
done
echo "STATUS        : Booting"
PRIVATE_IPADDR=$( openstack server show ${INSTANCE_ID} | grep addresses | sed 's/.*=\([0-9\.]*\).*/\1/' )
echo "PRIVATE IP    : ${PRIVATE_IPADDR}"
openstack server add floating ip ${INSTANCE_ID} ${IPADDR}

# wait for instance to come online if we need to ssh into it
READY=""
while [ "${READY}" != "0" ]; do
    openstack console log show $INSTANCE_ID | grep ' login: ' &> /dev/null
    READY=$?
done
echo "STATUS        : Running"

# run docker swarm init
# docker -H ${IPADDR}:2375 swarm init

# disable manager from getting any containers
docker -H ${IPADDR}:2375 node update --availability drain ${CLUSTER}-master.os.ncsa.edu

# get the cluster join token
JOIN_TOKEN=$( docker -H ${IPADDR}:2375 swarm join-token -q worker )
echo "TOKEN         : ${JOIN_TOKEN}"

# create clients
cat > /tmp/cluster-worker.sh << EOF
#cloud-config

coreos:
  units:
    - name: docker.service
      command: start
      enable: true
      drop-ins:
        - name: 10-docker-opts.conf
          content: |
            [Service]
            Environment="DOCKER_OPTS=$OPTS -H tcp://0.0.0.0:2375"
    - name: docker-swarm-join.service
      command: start
      content: |
        [Unit]
        Description=Joins a swarm

        [Service]
        Type=oneshot
        ExecStart=/bin/sh -c "docker swarm join --token ${JOIN_TOKEN} ${PRIVATE_IPADDR}:2377"
EOF

if [ $WORKERS -gt 0 ]; then
    for x in $( seq -f "%02g" $WORKERS ); do
        WORKER_ID=$( openstack server list | awk "/ ${CLUSTER}-worker-${x} / { print \$2 }" )
        if [ "${WORKER_ID}" == "" ]; then
            WORKER_ID=$( openstack server create ${NET_ID} --flavor ${FLAVOR} --key-name ${KEY} --security-group "${SECURITY}" --image ${IMAGE_ID} --user-data /tmp/cluster-worker.sh ${CLUSTER}-worker-${x} | awk "/^ | id / { print \$4 }" )
            echo "WORKER ${x}     : ${WORKER_ID}"
            if [ "$WAIT_WORKER" == "YES" ]; then
                READY=""
                while [ "${READY}" != "ACTIVE" ]; do
                    READY=$( openstack server show -c status ${WORKER_ID} | awk '/ status / { print $4}' )
                    if [ "${READY}" == "ERROR" ]; then
                        exit -1
                    fi
                done
                echo "STATUS        : Booting"
                WORKER_IPADDR=$( openstack server show ${WORKER_ID} | grep addresses | sed 's/.*=\([0-9\.]*\).*/\1/' )
                echo "PRIVATE IP    : ${WORKER_IPADDR}"
                # openstack server add floating ip ${WORKER_ID} ${TMPADDR}
                # wait for instance to come online if we need to ssh into it
                READY=""
                while [ "${READY}" != "0" ]; do
                  openstack console log show $WORKER_ID | grep ' login: ' &> /dev/null
                  READY=$?
                done
                echo "STATUS        : Running"
            fi
        fi
    done
fi

rm /tmp/cluster-worker.sh /tmp/cluster-manager.sh
