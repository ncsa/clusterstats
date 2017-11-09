FROM python:alpine
MAINTAINER Rob Kooper <kooper@illinois.edu>

ARG BUILD_VERSION

ENV LOGGER="" \
    SWARMS="" \
    DATADIR="/data" \
    USERS="" \
    BUILD=${BUILD_VERSION:-unknown}

VOLUME ["/data"]
RUN mkdir -p /data

WORKDIR /src

COPY requirements.txt /src
RUN pip install -r requirements.txt

COPY clusterstats /src/

ENTRYPOINT [ "python", "./server.py" ]
CMD [ "--help" ]
