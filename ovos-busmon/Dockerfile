FROM ghcr.io/home-assistant/base:latest

# ovos-busmon is used entirely unmodified (see DOCS.md) -- a real,
# actively-maintained FastAPI package from OpenVoiceOS itself
# (github.com/OpenVoiceOS/ovos-busmon), pip-installed as-is. No custom
# api.py bridge needed here, unlike ovos-persona/ovos-skills -- busmon
# already ships its own complete HTTP+SSE service, configured entirely
# via environment variables (see run.sh), and connects out to the
# shared bus this project's other add-ons already host rather than
# needing one hosted for it.
RUN apk add --no-cache python3 py3-pip \
 && pip install --no-cache-dir --break-system-packages ovos-busmon

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
