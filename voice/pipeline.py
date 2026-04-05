"""
voice/pipeline.py — MIRA Medical Appointment Voice Assistant
Variable names updated from ARIA. Core logic is identical and must not change:
  - messages[ai_count_before] fix preserved
  - Lock prevents concurrent utterances
  - TTS task cancellation on interruption
"""

import asyncio
import os
import sys

# Ensure project root is on the path when running voice/pipeline.py directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import HumanMessage, AIMessage
from graph.graph import mira_graph
from graph.state import initial_state, CallState


class MIRAVoicePipeline:
    def __init__(self):
        self.state: CallState = initial_state()
        self._tts_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def on_utterance(self, transcript: str, detected_lang: str = None) -> str:
        if not transcript.strip():
            return ""

        if self._tts_task and not self._tts_task.done():
            self._tts_task.cancel()
            print("[pipeline] TTS interrupted by patient")

        async with self._lock:
            # Stop processing if call already ended
            if self.state.get("phase") == "ended":
                return ""

            if detected_lang:
                lang_hint = "es" if detected_lang.startswith("es") else "en"
                self.state["preferred_language"] = lang_hint

            self.state["messages"].append(HumanMessage(content=transcript))
            self.state["turn_count"] = self.state.get("turn_count", 0) + 1

            # Count AI messages BEFORE graph runs — CRITICAL: do not change
            ai_count_before = sum(
                1 for m in self.state["messages"] if isinstance(m, AIMessage)
            )

            try:
                updated = await mira_graph.ainvoke(
                    self.state,
                    config={"recursion_limit": 25}
                )
                self.state = updated
            except Exception as e:
                print(f"[pipeline] Graph error: {e}")
                lang = self.state.get("preferred_language", "en")
                fallback = (
                    "Sorry about that — could you say that again?"
                    if lang == "en" else
                    "Lo siento, ¿podría repetir eso?"
                )
                return fallback

            # Get FIRST new AI message — preserves auth_agent's appointment delivery
            # Using messages[ai_count_before] not messages[-1] — DO NOT change
            all_ai = [m for m in self.state.get("messages", []) if isinstance(m, AIMessage)]
            new_ai = all_ai[ai_count_before:]

            if new_ai:
                mira_text = new_ai[0].content
            elif all_ai:
                mira_text = all_ai[-1].content
            else:
                mira_text = ""

            lang = self.state.get("preferred_language", "en")
            print(f"\n[MIRA/{lang.upper()}] {mira_text[:120]}")
            return mira_text

    async def greet(self) -> str:
        return await self.on_utterance("[CALL_CONNECTED]")

    async def init_state(self) -> None:
        """Initialise pipeline state without calling the LLM.
        Used when the greeting is pre-generated hardcoded audio."""
        self.state["phase"] = "auth_phone"
        self.state["turn_count"] = 0

    @property
    def is_ended(self) -> bool:
        return self.state.get("phase") == "ended"

    @property
    def current_language(self) -> str:
        return self.state.get("preferred_language", "en")


async def run_terminal_demo():
    """Full bilingual call simulation in terminal."""
    print("\n" + "═" * 64)
    print("  MIRA — RIVERSIDE MEDICAL CENTRE  |  Bilingual Demo")
    print("═" * 64)
    print("\n  Test numbers:")
    print("  4045550001 → Sarah Mitchell   (confirmed  | Cardiology)")
    print("  4045550002 → James Thornton   (pending    | Neurology)")
    print("  4045550003 → Emily Patel      (rescheduled| Dermatology)")
    print("  4045550004 → Michael Walsh    (cancelled  | Oncology)")
    print("  8135550005 → Diana Foster     (confirmed  | Orthopaedics)")
    print("  8005550010 → Maria Gonzalez   (confirmed  | ES speaker)")
    print("  8005550011 → Carlos Mendoza   (rescheduled| ES speaker)")
    print("  9999999999 → unknown patient  (error path)")
    print()

    pipeline = MIRAVoicePipeline()
    greeting = await pipeline.greet()
    print(f"MIRA [EN]: {greeting}\n")

    while not pipeline.is_ended:
        try:
            user_input = input("You:  ").strip()
        except (EOFError, KeyboardInterrupt):
            user_input = "goodbye"
        if not user_input:
            continue
        response = await pipeline.on_utterance(user_input)
        if response:
            lang = pipeline.current_language.upper()
            print(f"MIRA [{lang}]: {response}\n")
        if pipeline.is_ended:
            break

    print("\n" + "═" * 64)
    print("  Call ended.")
    print("═" * 64 + "\n")


if __name__ == "__main__":
    import dotenv
    dotenv.load_dotenv()
    asyncio.run(run_terminal_demo())
