FROM ubuntu:bionic
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
            python3-selenium \
            python3-bs4 \
            python3-lxml \
            firefoxdriver \
            firefox \
            dumb-init \
        && apt-get -y autoclean \
        && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["/web_scraping.py"]
