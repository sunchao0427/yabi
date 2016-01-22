#
FROM muccg/yabi:next_release
MAINTAINER https://github.com/muccg/yabi/

ARG PIP_OPTS="--no-cache-dir"

ENV DEPLOYMENT dev
ENV PRODUCTION 0
ENV DEBUG 1

USER root
WORKDIR /app

COPY krb5.conf /etc/krb5.conf

# install python deps
COPY yabi/*requirements.txt /app/yabi/
COPY yabish/*requirements.txt /app/yabish/

RUN pip freeze
RUN pip ${PIP_OPTS} uninstall -y yabish
RUN pip ${PIP_OPTS} uninstall -y yabi
RUN pip ${PIP_OPTS} install --upgrade -r yabi/requirements.txt
RUN pip ${PIP_OPTS} install --upgrade -r yabish/requirements.txt

# Copy code and install the app
COPY . /app
RUN pip ${PIP_OPTS} install -e yabi
RUN pip ${PIP_OPTS} install -e yabish

EXPOSE 8000 9000 9001 9100 9101
VOLUME ["/app", "/data"]

# Allow celery to run as root for dev
ENV C_FORCE_ROOT=1
ENV HOME /data
WORKDIR /data

# entrypoint shell script that by default starts runserver
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["runserver"]
