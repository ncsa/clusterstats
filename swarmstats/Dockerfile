FROM python:3-onbuild
MAINTAINER Rob Kooper <kooper@illinois.edu>

ENV LOGGER="" \
    NODE="" \
    SWARMS="" \
    DATADIR="/data"

VOLUME ["/data"]

RUN mkdir -p /data

CMD [ "python", "./server.py"]
