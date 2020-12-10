FROM alpine:3.12 AS base
LABEL maintainer="Ean J Price <ean@pricepaper.com>"

# Generate locale 
ENV LANG en_US.utf8

COPY geckodriver /usr/local/bin

# Install some deps and wkhtmltopdf
RUN set -x; \
        apk update \
        && apk upgrade \
        && apk add \
            py3-lxml \
            py3-pip \
            firefox \
            dumb-init \
        && pip3 install --no-cache beautifulsoup4 selenium

FROM base AS final
# Copy base script
COPY web_scraping.py /

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["/web_scraping.py"]
