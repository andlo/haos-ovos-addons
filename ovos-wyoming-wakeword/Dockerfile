FROM ghcr.io/home-assistant/base:latest

# wyoming pinned to 1.5.4: wyoming-ovos-wakeword's own requirements.txt
# pins this exact version; see ovos-wyoming-tts/Dockerfile for why.
RUN apk add --no-cache python3 py3-pip jq \
 && pip install --no-cache-dir --break-system-packages \
      "wyoming==1.5.4" wyoming-ovos-wakeword ovos-ww-plugin-precise-lite

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
