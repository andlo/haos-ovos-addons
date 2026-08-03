FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache python3 py3-pip jq \
 && pip install --no-cache-dir --break-system-packages \
      wyoming-ovos-wakeword ovos-ww-plugin-precise-lite

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
