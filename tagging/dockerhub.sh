#!/bin/bash

# DEBUG   : set to echo to print command and not execute
# PUSH    : set to push to push, then push newtag to docker hub

#DEBUG=echo
PUSH=${PUSH:-""}

echo -e "inputs: \$1 username, \$2 passwwd, \$3 project keyword"

USER=$1
PASSWD=$2
PROJ_KEYWORD=$3
TAG=latest

# new tag to be pushed on docker hub
NewTag=browndog

if [ -z "$1" ] || [ -z "$2" ]
then
    echo "failed to give all input params"
    exit 128
fi

case "${PROJ_KEYWORD}" in
    POL*)     PROJECT=ncsapolyglot;;
    CATS*)    PROJECT=clowder;;
    *)        echo "UNKNOWN:${PROJ_KEYWORD}"; exit 128
esac

read -a names <<< $(./bitbucket.sh $USER $PASSWD $PROJ_KEYWORD names)

if [ 0 == "$?" ]
then
    for name in "${names[@]}"
    do
        ${DEBUG} docker pull ${PROJECT}/$name:${TAG}
        ${DEBUG} docker tag ${PROJECT}/$name:${TAG} ${PROJECT}/$name:$NewTag
        if [ "$PUSH" = "push" ]; then
          ${DEBUG} docker push ${PROJECT}/${name}:${NewTag}
        fi
    done
fi

