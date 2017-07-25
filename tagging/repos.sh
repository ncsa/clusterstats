#!/bin/bash

#DEBUG=echo

# tag on repository
TAG=browndog_v0.2.0

if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ] || [ -z "$4" ]
then
    echo "\$1 username, \$2 passwd, \$3 tag/untag, \$4 project keyword (POL, CATS)"
    exit 128
fi

USER=$1
PASSWD=$2

tag=tag
if [[ $3 == "untag" ]]; then
  tag=untag
  TagDelete=-d
  TagColon=:
fi

PROJ_KEYWORD=$4

case "${PROJ_KEYWORD}" in
    POL*)     PROJECT=ncsapolyglot;;
    CATS*)    PROJECT=clowder;;
    *)        echo "UNKNOWN:${PROJ_KEYWORD}"; exit 128
esac


echo "auto" ${tag} ${TAG} ${PROJ_KEYWORD}

giturls=$(./bitbucket.sh $USER $PASSWD $PROJ_KEYWORD urls)

if [ 0 == "$?" ]
then
	read -a urls <<< $giturls
    for url in "${urls[@]}"
    do
        ${DEBUG} git clone $url
    done
else
	echo "failed to run ./bitbucket.sh"
	exit 128
fi

for d in $(find $(pwd) -mindepth 1 -maxdepth 1 -type d)
do
  ${DEBUG} cd $d
  ${DEBUG} git pull origin master
  ${DEBUG} git checkout master
  ${DEBUG} git tag $TagDelete $TAG
  ${DEBUG} git push origin $TagColon$TAG
  ${DEBUG} rm -rf $d
done
