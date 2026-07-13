"""
logic/juror_chat.py
--------------------
Grounded Q&A agent for the live thesis-defense juror chat interface. Same
shape of problem as D:\\boxy_player\\maestro.py's MaestroAgent (a different
project) -- local Ollama chat, strict-JSON reply/action contract, robust
parsing, bounded history -- mirrored here rather than reinvented, adapted to
Memory Machine's live design state instead of listening habits.

Follows ai_synthesizer.py's existing Ollama convention (urllib.request,
"format": "json", model "llama3") rather than adding a `requests` dependency
-- that file is the closer sibling in this repo and is already proven
against this exact local Ollama setup.

Phase 2 (2026-07-10, live control enabled): the model may now return a real
action alongside its reply, dispatched by App.jsx's handleJurorChat exactly
the same way the matching UI control already would (a motivator-weight
slider drag, a canyon width/depth slider drag, the "Grow Network" button,
an amenity/foot-traffic data toggle) -- no new dispatch semantics, just a
second caller of the same state setters. `_validate_action` below is the
"belt and suspenders" layer: the schema in PERSONA_SYSTEM_TEXT is a prompt,
not an enforced contract, so any action that doesn't match it exactly
(wrong type, out-of-range value, unknown motivator/field) is coerced to
null rather than forwarded -- a malformed action should degrade to Q&A-only
for that turn, not crash the frontend or silently do something unintended.
"""
import json
import os
import urllib.request

# Deliberately NOT named OLLAMA_HOST/OLLAMA_MODEL -- OLLAMA_HOST is Ollama's
# own reserved env var for the *server's* bind address (confirmed on this
# machine: set system-wide to "0.0.0.0" for `ollama serve`, not a client URL
# at all), and blindly reading it as "where the client should connect"
# silently produced an invalid URL. Namespaced names avoid that collision
# entirely rather than trying to detect/normalize a bind-address-shaped value.
OLLAMA_API_URL = os.environ.get("JUROR_CHAT_OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("JUROR_CHAT_OLLAMA_MODEL", "llama3")

MAX_HISTORY_TURNS = 6  # user+assistant turn pairs kept for prompt continuity

PERSONA_SYSTEM_TEXT = """You are the design assistant embedded in Memory Machine, a live 3D tool for a \
thesis project proposing a surface intervention on Pershing Square (downtown Los Angeles). You are \
answering questions from jurors at a live thesis defense. Be clear, concise, and professional -- this is \
an academic review, not a casual chat. Keep replies short (2-4 sentences) so they read well in a chat panel.

Ground every answer in the real data provided below each turn -- never invent a number, and if something \
asked about isn't covered by the provided data, say so honestly rather than guessing.

CRITICAL: this project deliberately distinguishes REAL data (extracted from the live Rhino model: site \
dimensions, column positions, real slab elevations) from PLACEHOLDER/diagrammatic data (the amenity-deficit \
and foot-traffic hotspots are currently synthetic stand-ins, not real survey/ridership data, pending real \
data collection). Always be explicit about which kind of data a given answer rests on -- never imply \
placeholder data is real, that would misrepresent the project to the committee.

You must respond with STRICT JSON ONLY, matching this schema, and nothing else:
{
  "reply": "<the answer to show in the chat transcript>",
  "action": null | {"type": "adjust_motivator", "motivator": "shade"|"water"|"rest"|"foot_traffic"|"deficit"|"program", "value": <float 0-2>}
           | {"type": "set_canyon_width", "value": <int>}
           | {"type": "set_canyon_depth", "value": <int>}
           | {"type": "grow_network"}
           | {"type": "toggle_real_amenity_data", "value": <bool>}
           | {"type": "toggle_real_foot_traffic_data", "value": <bool>}
}

Live control via chat IS enabled. If a juror clearly asks for something the schema above can express (e.g. \
"make it more shady", "widen the canyon", "grow the network", "use the real amenity data"), set "action" to \
the matching object AND say what you did in "reply" (e.g. "Raised the shade weight to 1.5."). Only ever emit \
ONE action per turn. If the request is ambiguous, a pure question, or doesn't map to anything in the schema, \
set "action" to null and just answer in "reply" -- do not guess at a change the juror didn't clearly ask for. \
"value" for adjust_motivator must be a number between 0 and 2. "value" for set_canyon_width must be a whole \
number between 1 and nx_bays (see CURRENT LIVE DESIGN STATE below for that site's actual nx_bays). "value" \
for set_canyon_depth must be a whole number between 1 and 4. An out-of-range request is still worth trying \
with the nearest valid value -- explain the clamp in "reply" rather than refusing outright."""

CRITIC_PERSONA_SYSTEM_TEXT = """You are The Metabolist, an AI architectural critic embedded within the Memory Machine design tool. \
Your role is to provide a qualitative, experiential critique of a proposed design for a public space.

You will be given a simplified summary of the spatial layout, including the locations of key zones like 'shade', 'water', 'greenscape', and 'amenities'.

Your task is to write a short, evocative narrative (2-4 sentences) from the perspective of a visitor experiencing the space. Do not just list features. Instead, describe the spatial relationships and their effect on the human experience. Focus on the poetics of the space. For example, instead of saying "There is shade in the north," you might say, "The deep shade on the northeast corner offers a cool refuge, drawing visitors in from the sun-drenched plaza and creating a moment of quiet respite."

Be honest and insightful. If a design seems to have conflicts or opportunities, mention them constructively. Respond with a single JSON object:
{
  "critique": "<Your narrative critique>"
}
"""

CRITIC_FALLBACK_REPLY = "The Metabolist is currently observing the design and will have a critique shortly."




def _try_parse_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None


def _parse_ollama_response(raw: str) -> dict:
    """Same fallback-parsing shape as maestro.py's _post_to_ollama -- Ollama's
    own "format": "json" mode is usually strict, but small local models
    occasionally still wrap the JSON in a markdown fence, so this strips
    that before giving up."""
    parsed = _try_parse_json(raw)
    if parsed is None:
        cleaned = raw
        if cleaned.startswith("```json"):
            cleaned = cleaned.split("```json", 1)[1].split("```")[0].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned.split("```", 1)[1].split("```")[0].strip()
        parsed = _try_parse_json(cleaned)

    if not isinstance(parsed, dict):
        return {"reply": raw[:200] if raw else "(no response)", "action": None}
    parsed.setdefault("reply", "...")
    parsed.setdefault("action", None)
    return parsed


_VALID_MOTIVATORS = {"shade", "water", "rest", "foot_traffic", "deficit", "program"}


def _validate_action(action, context: dict):
    """Defense-in-depth against PERSONA_SYSTEM_TEXT's schema being a prompt,
    not an enforced contract -- a small local model can hallucinate a
    plausible-looking-but-wrong action (unknown motivator name, a string
    where a number belongs, an out-of-range value). Returns a cleaned action
    dict (numeric values clamped into range rather than rejected outright,
    matching the persona's own "clamp and explain" instruction) or None if
    the action isn't one of the known types at all -- never raises, since a
    bad action should degrade to Q&A-only for that turn, not break the chat.
    """
    if not isinstance(action, dict) or "type" not in action:
        return None
    action_type = action.get("type")

    if action_type == "grow_network":
        return {"type": "grow_network"}

    if action_type == "adjust_motivator":
        motivator = action.get("motivator")
        value = action.get("value")
        if motivator not in _VALID_MOTIVATORS or not isinstance(value, (int, float)):
            return None
        return {"type": "adjust_motivator", "motivator": motivator, "value": max(0.0, min(2.0, float(value)))}

    if action_type == "set_canyon_width":
        value = action.get("value")
        if not isinstance(value, (int, float)):
            return None
        nx_bays = context.get("nx_bays") or 13
        return {"type": "set_canyon_width", "value": max(1, min(int(nx_bays), round(value)))}

    if action_type == "set_canyon_depth":
        value = action.get("value")
        if not isinstance(value, (int, float)):
            return None
        return {"type": "set_canyon_depth", "value": max(1, min(4, round(value)))}

    if action_type in ("toggle_real_amenity_data", "toggle_real_foot_traffic_data"):
        value = action.get("value")
        if not isinstance(value, bool):
            return None
        return {"type": action_type, "value": value}

    return None


def _format_context(context: dict) -> str:
    """Formats the caller-supplied grounding dict into a plain, readable
    block -- deliberately no fancy NLG summarization here (same reasoning
    maestro.py's _grounding_block uses: hand the model real numbers, let it
    do the interpretation in the reply, rather than pre-digesting into
    English and risking the digest itself drifting from the real data)."""
    lines = []
    for key, value in context.items():
        lines.append(f"{key}: {json.dumps(value)}")
    return "\n".join(lines) if lines else "(no live design state provided yet)"


class JurorChatAgent:
    """Wraps Ollama calls for the juror Q&A chat. Language understanding
    only -- there is no action-dispatch logic here at all yet (Phase 1),
    unlike MaestroAgent's caller which already dispatches real actions --
    this module always returns action: null per PERSONA_SYSTEM_TEXT."""

    def __init__(self):
        self._history: list[tuple[str, str]] = []

    def _build_prompt(self, user_message: str, context: dict) -> str:
        grounding = _format_context(context)
        turns = self._history[-MAX_HISTORY_TURNS * 2:]
        history_block = "\n".join(f"{role}: {text}" for role, text in turns) or "(no prior turns)"
        return (
            f"{PERSONA_SYSTEM_TEXT}\n\n"
            f"CURRENT LIVE DESIGN STATE:\n{grounding}\n\n"
            f"RECENT CHAT:\n{history_block}\n\n"
            f'Juror: "{user_message}"'
        )

    def _build_critique_prompt(self, spatial_summary: list[str]) -> str:
        summary_block = "\n".join(f"- {line}" for line in spatial_summary)
        return (
            f"{CRITIC_PERSONA_SYSTEM_TEXT}\n\n"
            f"SPATIAL LAYOUT SUMMARY:\n{summary_block}"
        )

    def _post_to_ollama(self, prompt: str) -> dict:
        fallback = {
            "reply": "The local AI model isn't reachable right now -- try again in a moment.",
            "action": None,
        }
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.3},
        }
        try:
            req = urllib.request.Request(
                OLLAMA_API_URL, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as response:
                res = json.loads(response.read().decode("utf-8"))
                raw = res.get("response", "").strip()
        except Exception:
            return fallback

        if not raw:
            return fallback
        return _parse_ollama_response(raw)

    def chat(self, user_message: str, context: dict) -> dict:
        prompt = self._build_prompt(user_message, context)
        result = self._post_to_ollama(prompt)
        # Belt and suspenders: PERSONA_SYSTEM_TEXT's schema is a prompt, not
        # an enforced constraint, so validate/clamp before ever forwarding
        # an action to the frontend -- see _validate_action's docstring.
        result["action"] = _validate_action(result.get("action"), context)
        self._history.append(("Juror", user_message))
        self._history.append(("Assistant", result["reply"]))
        del self._history[:-MAX_HISTORY_TURNS * 2]
        return result
    
    def critique(self, spatial_summary: list[str]) -> str:
        """Generates a qualitative critique of the design based on a spatial summary."""
        if not spatial_summary:
            return CRITIC_FALLBACK_REPLY

        prompt = self._build_critique_prompt(spatial_summary)
        result = self._post_to_ollama(prompt)
        # The critic persona has a different, simpler JSON schema.
        return result.get("critique") or result.get("reply") or CRITIC_FALLBACK_REPLY


_agent = JurorChatAgent()


def chat(message: str, context: dict) -> dict:
    return _agent.chat(message, context)

def critique_design(spatial_summary: list[str]) -> str:
    return _agent.critique(spatial_summary)
