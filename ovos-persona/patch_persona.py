"""Build-time patch for https://github.com/OpenVoiceOS/ovos-persona-server/pull/67

run_chat()/run_stream()'s stateless path passes raw OpenAI-style message
dicts straight to Persona.chat/stream, whose type contract is
List[AgentMessage] — QuestionSolver-based plugins then crash on
messages[-1].content. Remove this file and the Dockerfile step that runs
it once PR #67 is merged and a new PyPI/git ref includes the fix.
"""
import ovos_persona_server.persona as p

path = p.__file__
src = open(path).read()

helper = '''

def _dicts_to_agent_messages(messages):
    out = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            parts = [(x.get("text") or "") if isinstance(x, dict) else str(x) for x in content]
            content = " ".join(x for x in parts if x)
        elif content is not None and not isinstance(content, str):
            content = str(content)
        try:
            role = MessageRole(m.get("role") or "user")
        except ValueError:
            role = MessageRole.USER
        out.append(AgentMessage(role, content or ""))
    return out
'''

marker = "def run_chat("
assert marker in src and "_dicts_to_agent_messages" not in src, \
    "upstream source changed, patch_persona.py needs updating"
src = src.replace(marker, helper.strip("\n") + "\n\n\n" + marker, 1)

old_chat = "return persona.chat(messages, sess=sess)"
old_stream = "return persona.stream(messages, sess=sess)"
assert src.count(old_chat) == 1 and src.count(old_stream) == 1, \
    "call sites changed, patch_persona.py needs updating"
src = src.replace(old_chat, "return persona.chat(_dicts_to_agent_messages(messages), sess=sess)", 1)
src = src.replace(old_stream, "return persona.stream(_dicts_to_agent_messages(messages), sess=sess)", 1)

open(path, "w").write(src)
print(f"patched {path}")
