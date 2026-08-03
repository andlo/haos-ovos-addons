FROM ghcr.io/home-assistant/base:latest

# build-base + portaudio-dev: pyaudio (a transitive dependency, likely
# pulled in by the wakeword plugin stack) has no prebuilt wheel for this
# base image and must compile from source, needing a C compiler and
# PortAudio's headers. Left installed rather than stripped afterwards —
# pyaudio's compiled extension links against libportaudio at runtime, and
# apk's dependency tracking makes it unclear whether stripping the -dev
# package would also remove that runtime .so as an orphaned dependency.
# Worth revisiting once this add-on is stable and image size matters more
# than avoiding a fresh footgun.
RUN apk add --no-cache python3 py3-pip jq build-base portaudio-dev python3-dev \
 && pip install --no-cache-dir --break-system-packages \
      setuptools wyoming-ovos-wakeword ovos-ww-plugin-precise-lite

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
