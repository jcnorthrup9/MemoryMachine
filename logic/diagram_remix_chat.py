"""
logic/diagram_remix_chat.py
----------------------------
Conversational wrapper around the already-built Precedent Remixer pipeline
(logic.ai_synthesizer.generate_spatial_seed + logic.urban_engine.remix_layers)
for diagram_tool's (port 8006) AI Remix panel. diagram_tool itself never had
any AI/remix code (confirmed 2026-07-17 -- it was forked 2026-07-14 purely to
decouple its dev-server lifecycle from Pershing Metabolizer's, staying
explicitly "2D zone-layer placement... no AI ... generation" per its own
module docstring); the real prompt->LLM-picks-layers pipeline has only ever
lived in the MAIN app (logic/pershing_api.py's remix_precedent(), driving
PrecedentRemixerPanel.jsx). This module reuses that same pipeline unmodified
and adds the one missing piece: a real back-and-forth conversation, instead
of a single one-shot prompt.

Mirrors logic/juror_chat.py's JurorChatAgent history pattern exactly (same
shape of problem: bounded in-process turn history folded into the prompt)
rather than inventing a new conversation mechanism. Unlike JurorChatAgent,
there's no separate persona system-prompt to extend here -- history is
folded straight into the free-text `prompt` string generate_spatial_seed()
already accepts, so ai_synthesizer.py needs zero changes.

Deliberately returns only `narrative` + `layers` (remix_layers()'s own
{site, layerId, transform:{x_frac,y_frac,scale,rot}, ...} shape) -- not the
rasterized `grids`/`counts`/`attractor_points` remix_precedent() also
computes for the main app. Those are specific to baking into the 3D
TerracingEngine's paint masks; diagram_tool only needs the layer picks to
seed its own MemoryState.stack, in precedent-SVG-unit-fraction space, same
as everywhere else in this codebase keeps that math client-side.
"""
from logic.ai_synthesizer import generate_spatial_seed
from logic.urban_engine import remix_layers

MAX_HISTORY_TURNS = 6  # designer+AI turn pairs kept for prompt continuity


class DiagramRemixChatAgent:
    def __init__(self):
        self._history: list[tuple[str, str]] = []

    def _composite_prompt(self, user_message: str) -> str:
        turns = self._history[-MAX_HISTORY_TURNS * 2:]
        if not turns:
            return user_message
        history_block = "\n".join(f"{role}: {text}" for role, text in turns)
        return (
            f"Ongoing design conversation so far:\n{history_block}\n\n"
            f"Latest request: {user_message}"
        )

    def remix(self, user_message: str) -> dict:
        composite = self._composite_prompt(user_message)
        seed_items, narrative = generate_spatial_seed(composite)
        layers = remix_layers(seed_items)
        self._history.append(("Designer", user_message))
        self._history.append(("AI", narrative))
        del self._history[:-MAX_HISTORY_TURNS * 2]
        return {"narrative": narrative, "layers": layers}

    def reset(self):
        self._history = []


_agent = DiagramRemixChatAgent()


def remix(message: str) -> dict:
    return _agent.remix(message)


def reset():
    _agent.reset()
