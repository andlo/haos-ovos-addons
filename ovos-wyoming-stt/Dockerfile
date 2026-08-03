FROM ghcr.io/home-assistant/base:latest

# wyoming pinned to 1.5.4: wyoming-ovos-stt itself declares no upper bound,
# but the sibling wyoming-ovos-tts/wakeword projects pin exactly this
# version, and newer wyoming releases break the TtsVoice/AsrVoice API.
RUN apk add --no-cache python3 py3-pip jq \
 && pip install --no-cache-dir --break-system-packages \
      "wyoming==1.5.4" wyoming-ovos-stt ovos-stt-plugin-server

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
