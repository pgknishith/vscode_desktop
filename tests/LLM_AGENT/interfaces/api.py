from typing import Any, Dict

from core.agent import Agent


def run_goal(
    goal: str,
    max_steps: int = 20,
    dry_run: bool | None = None,
    speak: bool | None = None,
    voice_enabled: bool | None = None,
) -> Dict[str, Any]:
    agent = Agent(max_steps=max_steps, dry_run=dry_run, voice_enabled=voice_enabled)
    return agent.run(goal, speak=speak)


def chat(
    message: str,
    speak: bool | None = None,
    auto_run: bool = False,
    max_steps: int = 20,
    dry_run: bool | None = None,
    voice_enabled: bool | None = None,
) -> Dict[str, Any]:
    agent = Agent(max_steps=max_steps, dry_run=dry_run, voice_enabled=voice_enabled)
    return agent.chat(message=message, speak=speak, auto_run=auto_run)


def list_voices() -> Dict[str, Any]:
    return Agent().voices()


def learn(
    topic: str,
    sources: list[str] | None = None,
    speak: bool | None = None,
    voice_enabled: bool | None = None,
) -> Dict[str, Any]:
    agent = Agent(voice_enabled=voice_enabled)
    return agent.learn(topic=topic, sources=sources, speak=speak)


def learning_status() -> Dict[str, Any]:
    return Agent().learning_status()
