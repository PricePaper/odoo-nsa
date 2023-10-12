FROM alpine:3.16 AS base
LABEL maintainer="Ean J Price <ean@pricepaper.com>"

# Generate locale 
ENV LANG en_US.utf8

COPY geckodriver /usr/local/bin

# Install some deps
RUN set -x; \
        adduser -D -u 29750 scrape \
        && mkdir /home/scrape/tmp /home/scrape/Downloads \
        && chown scrape:scrape /home/scrape/tmp /home/scrape/Downloads \
        && apk update \
        && apk upgrade \
        && apk add \
            py3-lxml \
            py3-pip \
            firefox \
            dumb-init \
            py3-beautifulsoup4 \
            py3-cffi \
            py3-wheel \
            py3-cryptography \
            py3-trio \
            py3-attrs \
            py3-outcome \
            py3-sortedcontainers \
            py3-sniffio \
            py3-async_generator \
            py3-wsproto \
            py3-openssl \
            py3-urllib3 \
            py3-pysocks \
            py3-certifi \
        && pip3 install --no-cache 'selenium<4.3' \
              multiprocessing_logging

FROM base AS final
# Copy base script
COPY web_scraping.py /home/scrape

USER scrape
WORKDIR /home/scrape
ENV TMPDIR /home/scrape/tmp
ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["/home/scrape/web_scraping.py"]
