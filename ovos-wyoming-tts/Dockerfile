FROM ghcr.io/home-assistant/base:latest

# wyoming pinned to 1.5.4: wyoming-ovos-tts's own requirements.txt pins this
# exact version; newer wyoming releases changed the TtsVoice API and crash
# the bridge at startup (TypeError: TtsVoice.__init__() missing 'version').
RUN apk add --no-cache python3 py3-pip espeak-ng jq \
 && pip install --no-cache-dir --break-system-packages \
      "wyoming==1.5.4" wyoming-ovos-tts ovos-tts-plugin-server

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
