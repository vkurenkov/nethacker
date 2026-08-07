from __future__ import annotations

import argparse
import contextlib
import ctypes
import glob
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any

DEFAULT_ACTION_STALL_TIMEOUT_SECONDS = 60.0
NLE_CHALLENGE_NO_PROGRESS_STEPS = 10_000

_VALID_ROLE_VARIANTS: dict[str, frozenset[tuple[str, str]]] = {
    "arc": frozenset({("hum", "law"), ("hum", "neu"), ("dwa", "law"), ("gno", "neu")}),
    "bar": frozenset({("hum", "neu"), ("hum", "cha"), ("orc", "cha")}),
    "cav": frozenset({("hum", "law"), ("hum", "neu"), ("dwa", "law"), ("gno", "neu")}),
    "hea": frozenset({("hum", "neu"), ("gno", "neu")}),
    "kni": frozenset({("hum", "law")}),
    "mon": frozenset({("hum", "law"), ("hum", "neu"), ("hum", "cha")}),
    "pri": frozenset({("hum", "law"), ("hum", "neu"), ("hum", "cha"), ("elf", "cha")}),
    "ran": frozenset(
        {("hum", "neu"), ("hum", "cha"), ("elf", "cha"), ("gno", "neu"), ("orc", "cha")}
    ),
    "rog": frozenset({("hum", "cha"), ("orc", "cha")}),
    "sam": frozenset({("hum", "law")}),
    "tou": frozenset({("hum", "neu")}),
    "val": frozenset({("hum", "law"), ("hum", "neu"), ("dwa", "law")}),
    "wiz": frozenset(
        {("hum", "neu"), ("hum", "cha"), ("elf", "cha"), ("gno", "neu"), ("orc", "cha")}
    ),
}
_ROLE_ALIASES = {
    "archeologist": "arc",
    "barbarian": "bar",
    "caveman": "cav",
    "cavewoman": "cav",
    "healer": "hea",
    "knight": "kni",
    "monk": "mon",
    "priest": "pri",
    "priestess": "pri",
    "ranger": "ran",
    "rogue": "rog",
    "samurai": "sam",
    "tourist": "tou",
    "valkyrie": "val",
    "wizard": "wiz",
}
_RACE_ALIASES = {
    "human": "hum",
    "elf": "elf",
    "elven": "elf",
    "dwarf": "dwa",
    "dwarven": "dwa",
    "gnome": "gno",
    "gnomish": "gno",
    "orc": "orc",
    "orcish": "orc",
}
_ALIGNMENT_ALIASES = {
    "law": "law",
    "lawful": "law",
    "neu": "neu",
    "neutral": "neu",
    "cha": "cha",
    "chaotic": "cha",
}
_GENDER_ALIASES = {"mal": "mal", "male": "mal", "fem": "fem", "female": "fem"}
_WELCOME_PATTERN = re.compile(
    r"\bYou are an? (?P<alignment>lawful|neutral|chaotic) "
    r"(?P<gender>male|female) (?P<race>human|elven|dwarven|gnomish|orcish) "
    r"(?P<role>[A-Za-z]+)\."
)


def _normalize_character(character: str) -> str:
    if character.strip() == "@":
        return "@"
    parts = tuple(character.strip().lower().split("-"))
    if len(parts) != 4:
        raise ValueError(f"invalid NetHack character identity: {character}")
    role, race, alignment, gender = parts
    valid_gender = gender in ({"fem"} if role == "val" else {"mal", "fem"})
    if (race, alignment) not in _VALID_ROLE_VARIANTS.get(role, ()) or not valid_gender:
        raise ValueError(f"invalid NetHack character identity: {character}")
    return "-".join(parts)


def _character_from_xlog(fields: dict[str, str]) -> str | None:
    try:
        alignment = fields["align"] if "align" in fields else fields["alignment"]
        return _normalize_character(
            "-".join(
                (
                    _ROLE_ALIASES.get(fields["role"].lower(), fields["role"][:3].lower()),
                    _RACE_ALIASES[fields["race"].lower()],
                    _ALIGNMENT_ALIASES[alignment.lower()],
                    _GENDER_ALIASES[fields["gender"].lower()],
                )
            )
        )
    except (KeyError, ValueError):
        return None


def _character_from_observation(observation: dict[str, Any]) -> str | None:
    raw_message = observation.get("message")
    if raw_message is None:
        return None
    message = bytes(raw_message).split(b"\0", 1)[0].decode("utf-8", errors="replace")
    match = _WELCOME_PATTERN.search(message)
    if match is None:
        return None
    try:
        return _normalize_character(
            "-".join(
                (
                    _ROLE_ALIASES[match.group("role").lower()],
                    _RACE_ALIASES[match.group("race").lower()],
                    _ALIGNMENT_ALIASES[match.group("alignment")],
                    _GENDER_ALIASES[match.group("gender")],
                )
            )
        )
    except (KeyError, ValueError):
        return None


class AgentStepTimeout(KeyboardInterrupt):
    """Match AutoAscend's watchdog for policy cycles that stop taking game steps."""


def _run_with_step_watchdog(
    agent: Any,
    wrapper: Any,
    *,
    stall_seconds: float = DEFAULT_ACTION_STALL_TIMEOUT_SECONDS,
) -> None:
    if stall_seconds <= 0:
        raise ValueError("stall_seconds must be positive")
    stopped = threading.Event()
    agent_thread_id = threading.get_ident()

    def watch_steps() -> None:
        last_step_count = wrapper.step_count
        last_step_at = time.monotonic()
        poll_seconds = min(0.25, stall_seconds)
        while not stopped.is_set():
            if stopped.wait(poll_seconds):
                return
            step_count = wrapper.step_count
            if step_count != last_step_count:
                last_step_count = step_count
                last_step_at = time.monotonic()
                continue
            if time.monotonic() - last_step_at < stall_seconds:
                continue
            result = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(agent_thread_id),
                ctypes.py_object(AgentStepTimeout),
            )
            if result > 1:
                ctypes.pythonapi.PyThreadState_SetAsyncExc(
                    ctypes.c_ulong(agent_thread_id),
                    None,
                )
            return

    watchdog = threading.Thread(
        target=watch_steps,
        daemon=True,
        name="autoascend-step-watchdog",
    )
    watchdog.start()
    try:
        agent.main()
    finally:
        stopped.set()
        watchdog.join(timeout=stall_seconds + 1.0)


def _parse_xlog(path_pattern: str) -> dict[str, str]:
    lines: list[str] = []
    for path in glob.glob(path_pattern):
        try:
            lines.extend(Path(path).read_text(encoding="utf-8").splitlines())
        except OSError:
            continue
    if not lines:
        return {}
    fields: dict[str, str] = {}
    for token in lines[-1].split(":" if ":" in lines[-1] else "\t"):
        key, separator, value = token.partition("=")
        if separator:
            fields[key.strip()] = value.strip()
    return fields


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _episode_stop(
    *,
    end_status: Any,
    steps: int,
    max_steps: int,
    raw_terminated: bool,
    raw_truncated: bool,
) -> tuple[bool, bool, bool, str]:
    """Translate NLE's forced quit into explicit completion/censoring evidence."""
    aborted = _safe_int(end_status, 0) == -1
    if aborted:
        reason = "step_limit" if steps >= max_steps else "no_progress"
        return False, True, True, reason
    if raw_truncated:
        return False, True, True, "environment_truncated"
    if raw_terminated:
        return True, False, False, "game_over"
    return False, False, False, "incomplete"


def _progress_score(
    *, ascended: bool, max_depth: int, levels_visited: int, branches_visited: int, score: int
) -> float:
    if ascended:
        return 1.0
    depth_component = min(max(max_depth - 1, 0) / 49.0, 1.0)
    levels_component = min(levels_visited / 40.0, 1.0)
    branch_component = min(max(branches_visited - 1, 0) / 3.0, 1.0)
    score_component = min(math.log1p(max(score, 0)) / math.log1p(1_000_000), 1.0)
    return min(
        0.99,
        0.40 * depth_component
        + 0.20 * levels_component
        + 0.25 * branch_component
        + 0.15 * score_component,
    )


def run_episode(
    baseline: Path,
    seed: int,
    max_steps: int,
    *,
    character: str = "mon-hum-neu-mal",
    fix_time_effects: bool = True,
    no_progress_timeout: int = NLE_CHALLENGE_NO_PROGRESS_STEPS,
    action_stall_timeout: float = DEFAULT_ACTION_STALL_TIMEOUT_SECONDS,
    trace_output: Path | None = None,
) -> dict[str, Any]:
    if max_steps < 1:
        raise RuntimeError("episode step limit must be positive")
    if no_progress_timeout < 1:
        raise RuntimeError("no-progress timeout must be positive")
    if (
        isinstance(action_stall_timeout, bool)
        or not isinstance(action_stall_timeout, (int, float))
        or not math.isfinite(float(action_stall_timeout))
        or action_stall_timeout <= 0
    ):
        raise RuntimeError("action stall timeout must be positive")
    character = _normalize_character(character)
    started = time.monotonic()
    trace_path = trace_output.resolve() if trace_output is not None else None
    autoascend_path = baseline.resolve()
    if not (autoascend_path / "agent.py").is_file():
        raise RuntimeError(f"AutoAscend root is missing at {baseline}")

    sys.path.insert(0, str(autoascend_path))
    original_cwd = Path.cwd()
    os.chdir(autoascend_path)
    env = None
    wrapper = None
    agent = None
    error: str | None = None
    action_stalled = False
    trace_stream = None

    try:
        import numpy as np
        from agent import Agent
        from nle import nethack as nh
        from nle.env.tasks import NetHackChallenge

        class BotEnvironment:
            def __init__(self, raw_env: Any, action_trace: Any):
                self.env = raw_env
                self.action_trace = action_trace
                self.score = 0
                self.step_count = -1
                self.visualizer = None
                self.agent: Any = None
                self.last_info: dict[str, Any] = {}
                self.last_observation: dict[str, Any] | None = None
                self.raw_terminated = False
                self.raw_truncated = False
                self.max_depth = 1
                self.max_turns = 0
                self.levels_seen: set[tuple[int, int]] = set()
                self.branches_seen: set[int] = set()
                self.resolved_character: str | None = None

            @staticmethod
            def _normalize(observation: dict[str, Any]) -> dict[str, Any]:
                observation["tty_cursor"] = observation["tty_cursor"].astype(np.int32)
                return observation

            def reset(self) -> dict[str, Any]:
                observation, info = self.env.reset()
                observation = self._normalize(observation)
                self.score = 0
                self.step_count = -1
                self.last_info = info
                self.last_observation = observation
                self.raw_terminated = False
                self.raw_truncated = False
                self.resolved_character = _character_from_observation(observation)
                self._track(observation)
                return observation

            def _track(self, observation: dict[str, Any]) -> None:
                depth_index = getattr(nh, "NLE_BL_DEPTH", 12)
                dungeon_index = getattr(nh, "NLE_BL_DNUM", 23)
                level_index = getattr(nh, "NLE_BL_DLEVEL", 24)
                score_index = getattr(nh, "NLE_BL_SCORE", 9)
                time_index = getattr(nh, "NLE_BL_TIME", 20)
                blstats = observation.get("blstats")
                if blstats is None:
                    return
                self.max_depth = max(self.max_depth, _safe_int(blstats[depth_index], 1))
                self.score = _safe_int(blstats[score_index], self.score)
                self.max_turns = max(self.max_turns, _safe_int(blstats[time_index], 0))
                dungeon = _safe_int(blstats[dungeon_index], 0)
                level = _safe_int(blstats[level_index], 1)
                self.levels_seen.add((dungeon, level))
                self.branches_seen.add(dungeon)

            def step(self, action: Any) -> tuple[dict[str, Any], float, bool, dict[str, Any]]:
                action_index = nh.actions.ACTIONS.index(action)
                if self.action_trace is not None:
                    self.action_trace.write(bytes((action_index,)))
                observation, reward, terminated, truncated, info = self.env.step(action_index)
                observation = self._normalize(observation)
                self.step_count += 1
                self.last_info = info
                self.last_observation = observation
                self.raw_terminated = bool(terminated)
                self.raw_truncated = bool(truncated)
                self._track(observation)
                return observation, reward, bool(terminated or truncated), info

            def debug_tiles(self, *_args: Any, **_kwargs: Any) -> contextlib.AbstractContextManager:
                return contextlib.nullcontext()

            def debug_log(self, *_args: Any, **_kwargs: Any) -> contextlib.AbstractContextManager:
                return contextlib.nullcontext()

        with tempfile.TemporaryDirectory(prefix="nethacker-episode-") as savedir:
            if trace_path is not None:
                trace_stream = trace_path.open("wb")
            env = NetHackChallenge(
                max_episode_steps=max_steps,
                no_progress_timeout=no_progress_timeout,
                save_ttyrec_every=1,
                savedir=savedir,
                character=character,
                fix_moon_phase=fix_time_effects,
            )
            nethack_instance = env.unwrapped.nethack
            type(nethack_instance).set_initial_seeds(
                nethack_instance,
                seed,
                seed,
                False,
                None,
            )

            wrapper = BotEnvironment(env, trace_stream)
            wrapper.reset()
            agent = Agent(wrapper, seed=0, panic_on_errors=True)
            wrapper.agent = agent
            _run_with_step_watchdog(
                agent,
                wrapper,
                stall_seconds=action_stall_timeout,
            )
            xlog = _parse_xlog(str(Path(savedir) / "nle.*.xlogfile"))
    except BaseException as exc:
        action_stalled = isinstance(exc, AgentStepTimeout)
        error = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-4_000:]
        panics = getattr(agent, "all_panics", []) if agent is not None else []
        if "Cyclic Panic" in str(exc) and panics:
            root = panics[-1]
            root_error = "".join(
                traceback.format_exception(type(root), root, root.__traceback__)
            )[-4_000:]
            error = (error + "\nLast underlying panic:\n" + root_error)[-8_000:]
        xlog = {}
    finally:
        if trace_stream is not None:
            with contextlib.suppress(Exception):
                trace_stream.close()
        if env is not None:
            with contextlib.suppress(Exception):
                env.close()
        os.chdir(original_cwd)
        with contextlib.suppress(ValueError):
            sys.path.remove(str(autoascend_path))

    score = _safe_int(xlog.get("points"), getattr(wrapper, "score", 0))
    death = xlog.get("death", "")
    ascended = death.lower() == "ascended"
    last_info = getattr(wrapper, "last_info", {})
    end_status = last_info.get("end_status")
    steps = max(_safe_int(getattr(wrapper, "step_count", -1), -1) + 1, 0)
    terminated, truncated, censored, stop_reason = _episode_stop(
        end_status=end_status,
        steps=steps,
        max_steps=max_steps,
        raw_terminated=bool(getattr(wrapper, "raw_terminated", False)),
        raw_truncated=bool(getattr(wrapper, "raw_truncated", False)),
    )
    if error is not None and not censored:
        terminated = False
        stop_reason = "runner_error"
    if action_stalled:
        terminated = False
        truncated = True
        censored = True
        stop_reason = "action_stall"
    if censored or error is not None:
        status = stop_reason
    else:
        status = death or str(end_status if end_status is not None else stop_reason)
    max_depth = getattr(wrapper, "max_depth", 1)
    levels_visited = len(getattr(wrapper, "levels_seen", ()))
    branches_visited = len(getattr(wrapper, "branches_seen", ()))
    panic_count = len(getattr(agent, "all_panics", [])) if agent is not None else 0
    turns = getattr(wrapper, "max_turns", 0)
    resolved_code = _character_from_xlog(xlog)
    if resolved_code is None:
        resolved_code = getattr(wrapper, "resolved_character", None)
    if resolved_code is None and character != "@":
        resolved_code = character
    progress = _progress_score(
        ascended=ascended,
        max_depth=max_depth,
        levels_visited=levels_visited,
        branches_visited=branches_visited,
        score=score,
    )

    return {
        "seed": seed,
        "character": resolved_code or character,
        "requested_character": character,
        "resolved_character": resolved_code,
        "time_effects_fixed": fix_time_effects,
        "status": status,
        "score": score,
        "progress": progress,
        "ascended": ascended,
        "max_depth": max_depth,
        "levels_visited": levels_visited,
        "branches_visited": branches_visited,
        "milestone": branches_visited,
        "turns": turns,
        "steps": steps,
        "step_fraction": min(steps / max_steps, 1.0),
        "terminated": terminated,
        "truncated": truncated,
        "censored": censored,
        "stop_reason": stop_reason,
        "panic_count": panic_count,
        "crashed": error is not None,
        "error": error,
        "wall_time_seconds": time.monotonic() - started,
    }


def replay_episode(
    actions_path: Path,
    seed: int,
    max_steps: int,
    *,
    character: str = "mon-hum-neu-mal",
    fix_time_effects: bool = True,
    no_progress_timeout: int = NLE_CHALLENGE_NO_PROGRESS_STEPS,
) -> dict[str, Any]:
    """Derive authoritative metrics without importing candidate-controlled modules."""
    started = time.monotonic()
    if max_steps < 1:
        raise RuntimeError("episode step limit must be positive")
    if no_progress_timeout < 1:
        raise RuntimeError("no-progress timeout must be positive")
    character = _normalize_character(character)
    actions = actions_path.read_bytes()
    trace_digest = f"sha256:{hashlib.sha256(actions).hexdigest()}"
    if len(actions) > max_steps:
        raise RuntimeError("action trace exceeds the episode step limit")

    from nle import nethack as nh
    from nle.env.tasks import NetHackChallenge

    if any(action >= len(nh.actions.ACTIONS) for action in actions):
        raise RuntimeError("action trace contains an invalid NetHack action")

    env = None
    last_observation: dict[str, Any] | None = None
    last_info: dict[str, Any] = {}
    max_depth = 1
    max_turns = 0
    levels_seen: set[tuple[int, int]] = set()
    branches_seen: set[int] = set()
    finished = False
    raw_terminated = False
    raw_truncated = False
    steps_replayed = 0
    resolved_character: str | None = None

    def track(observation: dict[str, Any]) -> None:
        nonlocal max_depth, max_turns
        blstats = observation.get("blstats")
        if blstats is None:
            return
        depth = _safe_int(blstats[getattr(nh, "NLE_BL_DEPTH", 12)], 1)
        dungeon = _safe_int(blstats[getattr(nh, "NLE_BL_DNUM", 23)], 0)
        level = _safe_int(blstats[getattr(nh, "NLE_BL_DLEVEL", 24)], 1)
        turns = _safe_int(blstats[getattr(nh, "NLE_BL_TIME", 20)], 0)
        max_depth = max(max_depth, depth)
        max_turns = max(max_turns, turns)
        levels_seen.add((dungeon, level))
        branches_seen.add(dungeon)

    try:
        with tempfile.TemporaryDirectory(prefix="nethacker-replay-") as savedir:
            env = NetHackChallenge(
                max_episode_steps=max_steps,
                no_progress_timeout=no_progress_timeout,
                save_ttyrec_every=1,
                savedir=savedir,
                character=character,
                fix_moon_phase=fix_time_effects,
            )
            nethack_instance = env.unwrapped.nethack
            type(nethack_instance).set_initial_seeds(
                nethack_instance,
                seed,
                seed,
                False,
                None,
            )
            last_observation, last_info = env.reset()
            resolved_character = _character_from_observation(last_observation)
            track(last_observation)
            for action in actions:
                last_observation, _reward, terminated, truncated, last_info = env.step(action)
                steps_replayed += 1
                track(last_observation)
                if terminated or truncated:
                    raw_terminated = bool(terminated)
                    raw_truncated = bool(truncated)
                    finished = True
                    break
            if finished and steps_replayed != len(actions):
                raise RuntimeError("action trace continues after the episode terminated")
            xlog = _parse_xlog(str(Path(savedir) / "nle.*.xlogfile"))
    finally:
        if env is not None:
            with contextlib.suppress(Exception):
                env.close()

    blstats = (last_observation or {}).get("blstats")
    live_score = _safe_int(
        blstats[getattr(nh, "NLE_BL_SCORE", 9)] if blstats is not None else 0,
        0,
    )
    score = _safe_int(xlog.get("points"), live_score)
    death = xlog.get("death", "")
    ascended = death.lower() == "ascended"
    levels_visited = len(levels_seen)
    branches_visited = len(branches_seen)
    turns = max_turns
    resolved_code = _character_from_xlog(xlog)
    if resolved_code is None:
        resolved_code = resolved_character
    if resolved_code is None and character != "@":
        resolved_code = character
    end_status = last_info.get("end_status")
    terminated, truncated, censored, stop_reason = _episode_stop(
        end_status=end_status,
        steps=steps_replayed,
        max_steps=max_steps,
        raw_terminated=raw_terminated,
        raw_truncated=raw_truncated,
    )
    if not finished:
        stop_reason = "trace_exhausted"
    if censored:
        status = stop_reason
    elif finished:
        status = death or str(end_status if end_status is not None else stop_reason)
    else:
        status = "trace_exhausted"
    return {
        "seed": seed,
        "character": resolved_code or character,
        "requested_character": character,
        "resolved_character": resolved_code,
        "time_effects_fixed": fix_time_effects,
        "status": status,
        "score": score,
        "progress": _progress_score(
            ascended=ascended,
            max_depth=max_depth,
            levels_visited=levels_visited,
            branches_visited=branches_visited,
            score=score,
        ),
        "ascended": ascended,
        "max_depth": max_depth,
        "levels_visited": levels_visited,
        "branches_visited": branches_visited,
        "milestone": branches_visited,
        "turns": turns,
        "steps": steps_replayed,
        "step_fraction": min(steps_replayed / max_steps, 1.0),
        "terminated": terminated,
        "truncated": truncated,
        "censored": censored,
        "stop_reason": stop_reason,
        "panic_count": 0,
        "crashed": not finished,
        "error": None if finished else "candidate action trace ended before the episode",
        "wall_time_seconds": time.monotonic() - started,
        "steps_replayed": steps_replayed,
        "trace_digest": trace_digest,
        "evidence_source": "trusted_action_replay",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one trusted NetHack evaluation episode")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--baseline", type=Path)
    mode.add_argument("--replay-actions", type=Path)
    parser.add_argument("--trace-output", type=Path)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--character", default="mon-hum-neu-mal")
    parser.add_argument(
        "--fix-time-effects",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--max-steps", type=int, required=True)
    parser.add_argument(
        "--no-progress-timeout",
        type=int,
        default=NLE_CHALLENGE_NO_PROGRESS_STEPS,
    )
    parser.add_argument(
        "--action-stall-timeout",
        type=float,
        default=DEFAULT_ACTION_STALL_TIMEOUT_SECONDS,
    )
    args = parser.parse_args(argv)
    if args.replay_actions is not None:
        if args.trace_output is not None:
            parser.error("--trace-output is valid only with --baseline")
        result = replay_episode(
            args.replay_actions,
            args.seed,
            args.max_steps,
            character=args.character,
            fix_time_effects=args.fix_time_effects,
            no_progress_timeout=args.no_progress_timeout,
        )
    else:
        result = run_episode(
            args.baseline,
            args.seed,
            args.max_steps,
            character=args.character,
            fix_time_effects=args.fix_time_effects,
            no_progress_timeout=args.no_progress_timeout,
            action_stall_timeout=args.action_stall_timeout,
            trace_output=args.trace_output,
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
