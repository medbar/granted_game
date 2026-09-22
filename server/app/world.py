from __future__ import annotations

import math
from typing import Any

from .config import reactions_config, spell_settings
from .models import Vec2, WorldAction, WorldObject


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class WorldResolver:
    def __init__(self) -> None:
        self.config = reactions_config()
        self.spell_settings = spell_settings()

    def resolve(
        self,
        intent: dict[str, Any],
        targets: list[WorldObject],
        world_objects: list[WorldObject] | None = None,
    ) -> tuple[list[WorldAction], list[str]]:
        channels = self._channels(intent)
        actions: list[WorldAction] = []
        rules: list[str] = []
        for target in targets:
            target_actions, target_rules = self._apply_to_target(intent, channels, target)
            actions.extend(target_actions)
            rules.extend(target_rules)
        if channels["electricity"] > 0.08 and world_objects:
            propagated = {target.id for target in targets}
            for medium in targets:
                medium_tags = {tag.lower() for tag in medium.tags} | {medium.material.name.lower()}
                if "water" not in medium_tags and medium.material.wetness < self.config["electricity"]["wetness_threshold"]:
                    continue
                for candidate in world_objects:
                    if candidate.id in propagated:
                        continue
                    distance = math.hypot(
                        candidate.position.x - medium.position.x,
                        candidate.position.y - medium.position.y,
                    )
                    inside_medium = "water" in medium_tags and distance <= medium.radius + candidate.radius
                    wet_chain = candidate.material.wetness >= self.config["electricity"]["wetness_threshold"] and distance <= self.config["electricity"]["wet_chain_range"]
                    if not inside_medium and not wet_chain:
                        continue
                    electric_actions, electric_rules = self._electricity_actions(
                        channels["electricity"] * self.config["electricity"]["propagation_multiplier"],
                        intent["power"],
                        candidate,
                        propagated=True,
                    )
                    actions.extend(electric_actions)
                    rules.extend(electric_rules)
                    propagated.add(candidate.id)
        if not targets or self._should_spawn(intent):
            actions.append(self._spawn_effect(intent, channels))
            rules.append("RULE_EFFECT_ENTITY: persistent/runtime magic created")
        return actions, list(dict.fromkeys(rules))

    @staticmethod
    def _channels(intent: dict[str, Any]) -> dict[str, float]:
        matter, actions, movement = intent["matter"], intent["actions"], intent["movement"]
        return {
            "heat": max(matter.get("fire", 0.0), matter.get("heat", 0.0), actions.get("ignite", 0.0)),
            "cold": max(matter.get("cold", 0.0), matter.get("ice", 0.0) * 0.7, actions.get("freeze", 0.0)),
            "water": matter.get("water", 0.0),
            "electricity": matter.get("electricity", 0.0),
            "force": max(matter.get("force", 0.0), matter.get("air", 0.0) * 0.65, movement.get("push", 0.0), movement.get("pull", 0.0), actions.get("crush", 0.0)),
            "harm": max(actions.get("harm", 0.0), actions.get("destroy", 0.0), matter.get("decay", 0.0), matter.get("poison", 0.0)),
            "heal": max(actions.get("heal", 0.0), matter.get("life", 0.0)),
            "poison": matter.get("poison", 0.0),
            "lift": movement.get("lift", 0.0),
            "sharp": intent["properties"].get("sharp", 0.0),
            "crush": actions.get("crush", 0.0),
        }

    def _apply_to_target(
        self,
        intent: dict[str, Any],
        channels: dict[str, float],
        target: WorldObject,
    ) -> tuple[list[WorldAction], list[str]]:
        result: list[WorldAction] = []
        rules: list[str] = []
        power = intent["power"]
        material = target.material
        tags = {tag.lower() for tag in target.tags} | {material.name.lower()}
        state_names = {
            state if isinstance(state, str) else state.name
            for state in target.states
        }

        if channels["heat"] > 0.08:
            amount = channels["heat"] * power * self.config["heat"]["temperature_delta"]
            result.append(WorldAction(type="CHANGE_TEMPERATURE", target_id=target.id, amount=round(amount, 4)))
            rules.append("RULE_HEAT: heat increases temperature")
            next_temperature = material.temperature + amount
            if "ice" in tags and next_temperature >= self.config["phase_changes"]["ice_melts_at"]:
                result.append(WorldAction(type="CHANGE_MATERIAL_STATE", target_id=target.id, material="water"))
                rules.append("RULE_ICE_MELTS: heated ice becomes water")
            if "water" in tags and next_temperature >= self.config["phase_changes"]["water_boils_at"]:
                result.append(WorldAction(type="CHANGE_MATERIAL_STATE", target_id=target.id, material="steam"))
                result.append(self._radial_force(intent, target, power * self.config["heat"]["steam_force_multiplier"]))
                rules.append("RULE_WATER_BOILS: strongly heated water becomes steam")
                rules.append("RULE_STEAM_EXPANDS: rapid steam creates radial force")
            if material.flammability >= self.config["burning"]["flammability_threshold"] and channels["heat"] * power >= self.config["burning"]["ignition_strength"]:
                result.append(WorldAction(type="ADD_STATE", target_id=target.id, state="burning", strength=round(channels["heat"] * power, 4), duration=self.config["burning"]["duration"]))
                rules.append("RULE_BURNING: hot flammable matter ignites")
            if "living" in tags:
                result.append(WorldAction(type="DAMAGE", target_id=target.id, amount=round(self.config["heat"]["living_damage"] * channels["heat"] * power, 3)))
                rules.append("RULE_HEAT_LIVING: heat harms living matter")

        if channels["cold"] > 0.08:
            amount = -channels["cold"] * power * self.config["cold"]["temperature_delta"]
            result.append(WorldAction(type="CHANGE_TEMPERATURE", target_id=target.id, amount=round(amount, 4)))
            rules.append("RULE_COLD: cold decreases temperature")
            next_temperature = material.temperature + amount
            wants_freeze = intent["actions"].get("freeze", 0.0) > 0.28
            if "water" in tags and (next_temperature <= self.config["phase_changes"]["water_freezes_at"] or wants_freeze):
                result.append(WorldAction(type="CHANGE_MATERIAL_STATE", target_id=target.id, material="ice"))
                rules.append("RULE_WATER_FREEZES: cold water becomes ice")
            if "living" in tags:
                result.append(WorldAction(type="ADD_STATE", target_id=target.id, state="slowed", strength=round(channels["cold"] * power, 4), duration=self.config["cold"]["slowed_duration"]))
                rules.append("RULE_COLD_LIVING: cold slows living matter")
                if channels["cold"] * power >= self.config["cold"]["living_freeze_strength"]:
                    result.append(WorldAction(type="ADD_STATE", target_id=target.id, state="frozen", strength=round(channels["cold"] * power, 4), duration=self.config["cold"]["frozen_duration"]))
                    rules.append("RULE_DEEP_FREEZE: extreme cold temporarily freezes living matter")

        if channels["water"] > 0.12 and "water" not in tags and "ice" not in tags:
            wetness = min(1.0 - material.wetness, channels["water"] * power * self.config["water"]["wetness_scale"])
            result.append(WorldAction(type="CHANGE_WETNESS", target_id=target.id, amount=round(wetness, 4)))
            result.append(WorldAction(type="ADD_STATE", target_id=target.id, state="wet", strength=round(channels["water"], 4), duration=self.config["water"]["wet_duration"]))
            rules.append("RULE_WATER_WETS: water increases wetness")
            if "burning" in state_names:
                result.append(WorldAction(type="REMOVE_STATE", target_id=target.id, state="burning"))
                result.append(WorldAction(type="CHANGE_TEMPERATURE", target_id=target.id, amount=round(-self.config["water"]["extinguish_temperature_delta"] * channels["water"] * power, 4)))
                rules.append("RULE_WATER_EXTINGUISHES: water removes small burning effects")

        if channels["electricity"] > 0.08:
            electric_actions, electric_rules = self._electricity_actions(
                channels["electricity"], power, target
            )
            result.extend(electric_actions)
            rules.extend(electric_rules)

        if channels["force"] > 0.08:
            strength = channels["force"] * power * self.config["force"]["base_strength"] / max(material.mass, 0.15)
            result.append(self._directed_force(intent, target, strength))
            rules.append("RULE_FORCE_MASS: lighter objects accelerate more")

        if channels["lift"] > 0.08:
            result.append(WorldAction(type="ADD_STATE", target_id=target.id, state="levitating", strength=round(channels["lift"] * power, 4), duration=self.config["force"]["lift_duration"]))
            rules.append("RULE_LIFT: upward force creates temporary levitation")

        if channels["sharp"] > 0.08 and channels["force"] > 0.08:
            softness = max(self.config["sharp_force"]["minimum_softness"], 1.0 - material.hardness)
            damage = self.config["sharp_force"]["base_damage"] * channels["sharp"] * channels["force"] * power * softness
            result.append(WorldAction(type="DAMAGE", target_id=target.id, amount=round(damage, 3)))
            rules.append("RULE_SHARP_FORCE: sharp force damages soft matter more effectively")

        if channels["crush"] > 0.08:
            effectiveness = (
                self.config["crush"]["brittleness_base"]
                + material.brittleness * self.config["crush"]["brittleness_scale"]
            ) * (1.0 - material.hardness * self.config["crush"]["hardness_reduction"])
            damage = self.config["crush"]["base_damage"] * channels["crush"] * power * effectiveness
            result.append(WorldAction(type="DAMAGE", target_id=target.id, amount=round(damage, 3)))
            rules.append("RULE_CRUSH_MATERIAL: crushing depends on hardness and brittleness")

        if channels["poison"] > 0.08 and "living" in tags:
            result.append(WorldAction(type="ADD_STATE", target_id=target.id, state="poisoned", strength=round(channels["poison"] * power, 4), duration=self.config["poison"]["duration"]))
            rules.append("RULE_POISON_LIVING: poison adds damage over time to living matter")

        destroy = intent["actions"].get("destroy", 0.0)
        if destroy >= 0.75:
            result.append(WorldAction(type="DESTROY_OBJECT", target_id=target.id))
            rules.append("RULE_DESTROY: explicit destructive intent destroys its target")
        elif channels["harm"] > 0.08:
            result.append(WorldAction(type="DAMAGE", target_id=target.id, amount=round(self.config["harm"]["base_damage"] * channels["harm"] * power, 3)))
            rules.append("RULE_HARM: destructive intent reduces integrity")
        if channels["heal"] > 0.08 and "living" in tags:
            result.append(WorldAction(type="HEAL", target_id=target.id, amount=round(self.config["life"]["heal_amount"] * channels["heal"] * power, 3)))
            rules.append("RULE_LIFE: life energy restores living matter")
        return result, rules

    def _electricity_actions(
        self,
        electricity: float,
        power: float,
        target: WorldObject,
        propagated: bool = False,
    ) -> tuple[list[WorldAction], list[str]]:
        tags = {tag.lower() for tag in target.tags} | {target.material.name.lower()}
        conduction = target.material.conductivity
        rules: list[str] = []
        if target.material.wetness >= self.config["electricity"]["wetness_threshold"] or "water" in tags or "wet" in tags:
            conduction *= self.config["electricity"]["wet_conductivity_multiplier"]
            rules.append("RULE_WET_CONDUCTS: wet matter carries electricity better")
        damage = (
            self.config["electricity"]["base_damage"]
            + self.config["electricity"]["conductivity_damage"] * clamp(conduction)
        ) * electricity * power
        actions = [
            WorldAction(type="DAMAGE", target_id=target.id, amount=round(damage, 3)),
            WorldAction(type="ADD_STATE", target_id=target.id, state="electrified", strength=round(electricity * power, 4), duration=self.config["electricity"]["state_duration"]),
        ]
        rules.append("RULE_ELECTRICITY: conductivity controls electrical harm")
        if propagated:
            rules.append("RULE_ELECTRICITY_SPREADS: water carries electricity to nearby immersed or wet matter")
        return actions, rules

    @staticmethod
    def _directed_force(intent: dict[str, Any], target: WorldObject, strength: float) -> WorldAction:
        direction = intent["spatial"]["direction"].copy()
        origin = intent["spatial"]["origin"]
        if intent["movement"].get("push", 0.0) > 0.25 and (
            intent["targets"].get("around", 0.0) > 0.2 or intent["geometry"].get("ring", 0.0) > 0.35
        ):
            dx, dy = target.position.x - origin["x"], target.position.y - origin["y"]
            length = math.hypot(dx, dy) or 1.0
            direction = {"x": dx / length, "y": dy / length}
        if intent["movement"].get("pull", 0.0) > intent["movement"].get("push", 0.0):
            dx, dy = origin["x"] - target.position.x, origin["y"] - target.position.y
            length = math.hypot(dx, dy) or 1.0
            direction = {"x": dx / length, "y": dy / length}
        return WorldAction(type="APPLY_FORCE", target_id=target.id, direction=Vec2(**direction), strength=round(strength, 4))

    @staticmethod
    def _radial_force(intent: dict[str, Any], target: WorldObject, strength: float) -> WorldAction:
        origin = intent["spatial"]["origin"]
        dx, dy = target.position.x - origin["x"], target.position.y - origin["y"]
        length = math.hypot(dx, dy) or 1.0
        return WorldAction(type="APPLY_FORCE", target_id=target.id, direction=Vec2(x=dx / length, y=dy / length), strength=round(strength, 4))

    @staticmethod
    def _should_spawn(intent: dict[str, Any]) -> bool:
        return bool(intent["actions"].get("create", 0.0) > 0.15 or intent["geometry"] or not intent["targets"])

    def _spawn_effect(self, intent: dict[str, Any], channels: dict[str, float]) -> WorldAction:
        direction = intent["spatial"]["direction"]
        runtime_settings = self.spell_settings["runtime_effect"]
        speed = runtime_settings["base_speed"] + intent["properties"].get("fast", 0.0) * runtime_settings["fast_speed_bonus"]
        form = "field"
        if intent["geometry"].get("wall", 0.0) > 0.25:
            form = "wall"
        elif intent["geometry"].get("sphere", 0.0) > 0.25 or intent["geometry"].get("point", 0.0) > 0.25:
            form = "projectile"
        elif intent["geometry"].get("line", 0.0) > 0.45:
            form = "beam"
        elif intent["geometry"].get("ring", 0.0) > 0.25:
            form = "ring"
        return WorldAction(
            type="SPAWN_EFFECT_ENTITY",
            effect={
                "form": form,
                "payload": {**channels, "power": intent["power"]},
                "position": [intent["spatial"]["origin"]["x"], intent["spatial"]["origin"]["y"]],
                "velocity": [direction["x"] * speed, direction["y"] * speed],
                "radius": intent["spatial"]["radius"],
                "lifetime": intent["duration"],
            },
        )
