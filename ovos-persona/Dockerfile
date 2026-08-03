FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache python3 py3-pip jq \
 && pip install --no-cache-dir --break-system-packages \
      ovos-persona-server ovos-solver-ddg-plugin ovos-solver-wikipedia-plugin ovos-solver-failure-plugin

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
