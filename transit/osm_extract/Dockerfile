FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install --yes --no-install-recommends osmium-tool \
    && rm -rf /var/lib/apt/lists/*

COPY extract.sh /usr/local/bin/extract-r5-osm
RUN chmod +x /usr/local/bin/extract-r5-osm

ENTRYPOINT ["extract-r5-osm"]
