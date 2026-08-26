from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .gesture import GestureResolver
from .intent import SpellIntentBuilder
from .models import CastRequest, CastResponse, DebugInfo, Interpretation, SpellPlan
from .semantic import SemanticResolver
from .targeting import TargetResolver
from .visuals import VisualResolver
from .world import WorldResolver


class SpellService:
    def __init__(self, log_path: Path | None = None) -> None:
        self.semantic = SemanticResolver()
        self.gesture = GestureResolver()
        self.intent_builder = SpellIntentBuilder()
        self.targeting = TargetResolver()
        self.world = WorldResolver()
        self.visuals = VisualResolver()
        self.log_path = log_path

    def cast(self, request: CastRequest) -> CastResponse:
        started = time.perf_counter()
        anchors, coherence = self.semantic.resolve(request.spell_text)
        gesture = self.gesture.resolve(request.gesture, request.caster.position)
        intent = self.intent_builder.build(anchors, coherence, gesture, request.caster)
        targets = self.targeting.resolve(intent, request.caster, request.world.objects)
        actions, rules = self.world.resolve(intent, targets)
        visuals = self.visuals.resolve(intent, targets)
        elapsed = (time.perf_counter() - started) * 1000.0
        debug = DebugInfo(
            intent=intent,
            selected_targets=[target.id for target in targets],
            world_rules=rules,
            latency_ms=round(elapsed, 3),
        ) if request.options.debug else None
        response = CastResponse(
            request_id=request.request_id,
            interpretation=Interpretation(
                coherence=coherence,
                anchors=anchors,
                gesture_features=gesture,
            ),
            spell_plan=SpellPlan(
                duration=intent["duration"],
                power=intent["power"],
                effects=[],
                world_actions=actions,
                visuals=visuals,
            ),
            debug=debug,
        )
        if self.log_path and request.options.debug:
            self._append_log(request, response)
        return response

    def _append_log(self, request: CastRequest, response: CastResponse) -> None:
        record: dict[str, Any] = {
            "request": request.model_dump(mode="json"),
            "response": response.model_dump(mode="json"),
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

