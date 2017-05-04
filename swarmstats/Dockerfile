FROM python:3-onbuild
MAINTAINER Rob Kooper <kooper@illinois.edu>

ARG BUILD_VERSION

ENV LOGGER="" \
    SWARMS="" \
    DATADIR="/data" \
    USERS="" \
    BUILD=${BUILD_VERSION:-unknown}

VOLUME ["/data"]

RUN mkdir -p /data

CMD [ "python", "./server.py"]
