#!/bin/bash

USER=$1
PASSWD=$2
REPOS_KEYWORD=$3

ACTION=$4

function RepoNames() {
    echo "${repos}" | jq --arg PREFIX $PREFIX '.values[] | select((.slug | contains($PREFIX)) and (.state == "AVAILABLE")) | {name: .slug, clone: .links.clone} | .name' | tr -d '"'
}

function GitUrls() {
	echo "${repos}" | jq --arg PREFIX $PREFIX '.values[] | select((.slug | contains($PREFIX)) and (.state == "AVAILABLE")) | {name: .slug, clone: .links.clone}' | jq '.clone[] | select(.name == "http") | .href' | tr -d '"' 
}

if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ] || [ -z "$4" ]
then
    echo "failed to give all input params"
    exit 128
fi 

case "${REPOS_KEYWORD}" in
    POL*)     PREFIX="converters-";;
    CATS*)    PREFIX="extractors-";;
    *)        echo "UNKNOWN:${REPOS_KEYWORD}"; exit 128
esac

repos="$(curl -sH "Accept: application/json" -H "Content-type: application/json" -X GET https://${USER}:${PASSWD}@opensource.ncsa.illinois.edu/bitbucket/rest/api/1.0/projects/${REPOS_KEYWORD}/repos/)"

if [  0 -ne "$?" ]
then
    exit 128
fi

case "${ACTION}" in
    names*)   RepoNames;;
    urls*)    GitUrls;;
    *)        echo "UNKNOWN:${REPOS_KEYWORD}"; exit 128
esac
