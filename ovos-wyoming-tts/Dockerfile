FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache python3 py3-pip espeak-ng jq \
 && pip install --no-cache-dir --break-system-packages \
      wyoming-ovos-tts ovos-tts-plugin-server

# Upstream bug workaround: wyoming-ovos-tts's TtsProgram(...) call correctly
# passes version=__version__, but the nested TtsVoice(...) call forgets to,
# which crashes at startup against wyoming>=1.9 (TtsVoice.__init__() missing
# 1 required positional argument: 'version'). Patch it in place until fixed
# upstream. See: https://github.com/OpenVoiceOS/wyoming-ovos-tts
RUN python3 -c "\
import wyoming_ovos_tts.__main__ as m; \
path = m.__file__; \
src = open(path).read(); \
old = '                        installed=True,\n                        languages=languages,\n                    )\n                ],\n            )\n        ],\n    )'; \
new = '                        installed=True,\n                        version=__version__,\n                        languages=languages,\n                    )\n                ],\n            )\n        ],\n    )'; \
assert src.count(old) == 1, 'upstream source changed, patch needs updating'; \
open(path, 'w').write(src.replace(old, new, 1))"

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
