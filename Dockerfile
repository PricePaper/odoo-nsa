FROM ubuntu:focal
LABEL maintainer="Ean J Price <ean@pricepaper.com>"

# Generate locale 
ENV LANG en_US.utf8

# Copy base script
COPY web_scraping.py geckodriver /
RUN set -x; chmod +x /web_scraping.py ./geckodriver

# Install some deps and wkhtmltopdf
RUN set -x; \
        apt-get update \
        && apt-get install -y locales \
        && localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8 \
        && apt-get -y upgrade \
        && apt-get install -y --no-install-recommends \
            python3-lxml \
            firefox-geckodriver \
            python3-pip \
            firefox \
            dumb-init \
        && pip3 install --no-cache beautifulsoup4 selenium \
        && apt-get -y autoclean \
        && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["/web_scraping.py"]
