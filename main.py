"""
Voice-Controlled Game Map — Main loop.
PTT UI: hold button or Space to record → transcription → LLM → state.
"""

from __future__ import annotations

import json
import os
import sys
import threading

import colorama

from audio_listener import (
    listen_and_transcribe,
    start_ptt_recording,
    stop_ptt_recording,
    transcribe_audio_bytes,
)
from game_state import GameMap
from llm_interface import (
    SYSTEM_PROMPT,
    chat_with_tools,
    create_client,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    format_state_for_llm,
)

colorama.init(autoreset=True)

GREEN = colorama.Fore.GREEN
YELLOW = colorama.Fore.YELLOW
CYAN = colorama.Fore.CYAN
MAGENTA = colorama.Fore.MAGENTA
RED = colorama.Fore.RED
DIM = colorama.Style.DIM


def clear_console() -> None:
    if sys.platform == "win32":
        os.system("cls")
    else:
        os.system("clear")


def format_state_string(game: GameMap) -> str:
    """Return current map state as a plain string (for UI)."""
    snap = game.snapshot()
    lines = [
        "========== GAME MAP STATE ==========",
        "Locations: " + ", ".join(snap["locations"]),
        "",
        "Knights:",
    ]
    for k in snap["knights"]:
        lines.append(f"  {k['id']}  {k['name']} @ {k['location']}")
    if not snap["knights"]:
        lines.append("  (none)")
    lines.extend(["", "Dragon spots:"])
    for d in snap["dragon_spots"]:
        lines.append(f"  {d['id']}  {d['location']}  type={d['type']}  status={d['status']}")
    if not snap["dragon_spots"]:
        lines.append("  (none)")
    lines.extend(["", "Targets:"])
    for t in snap["targets"]:
        link = f" (linked: {t['linked_dragon_spot_id']})" if t.get("linked_dragon_spot_id") else ""
        lines.append(f"  {t['id']}  {t['location']}{link}  status={t['status']}")
    if not snap["targets"]:
        lines.append("  (none)")
    lines.append("======================================")
    return "\n".join(lines)


def pretty_print_state(game: GameMap) -> None:
    """Clear screen and print current map state with colors."""
    clear_console()
    snap = game.snapshot()
    print(CYAN + "========== GAME MAP STATE ==========" + colorama.Style.RESET_ALL)
    print(DIM + "Locations: " + ", ".join(snap["locations"]) + colorama.Style.RESET_ALL)
    print()
    print(MAGENTA + "Knights:" + colorama.Style.RESET_ALL)
    for k in snap["knights"]:
        print(f"  {k['id']}  {k['name']} @ {k['location']}")
    if not snap["knights"]:
        print("  (none)")
    print()
    print(MAGENTA + "Dragon spots:" + colorama.Style.RESET_ALL)
    for d in snap["dragon_spots"]:
        print(f"  {d['id']}  {d['location']}  type={d['type']}  status={d['status']}")
    if not snap["dragon_spots"]:
        print("  (none)")
    print()
    print(MAGENTA + "Targets:" + colorama.Style.RESET_ALL)
    for t in snap["targets"]:
        link = f" (linked: {t['linked_dragon_spot_id']})" if t.get("linked_dragon_spot_id") else ""
        print(f"  {t['id']}  {t['location']}{link}  status={t['status']}")
    if not snap["targets"]:
        print("  (none)")
    print(CYAN + "======================================" + colorama.Style.RESET_ALL)
    print()


def execute_tool(game: GameMap, name: str, arguments: dict) -> str:
    """Run the corresponding GameMap method; return result message."""
    try:
        if name == "move_knight":
            return game.move_knight(
                to_location_name=arguments["to_location_name"],
                knight_name=arguments.get("knight_name"),
            )
        if name == "create_dragon_spot":
            return game.create_dragon_spot(
                location_name=arguments["location_name"],
                dragon_type=arguments["dragon_type"],
            )
        if name == "create_target":
            return game.create_target(
                location_name=arguments.get("location_name"),
                linked_dragon_spot_id=arguments.get("linked_dragon_spot_id"),
            )
        if name == "attack_target":
            return game.attack_target(
                target_id=arguments["target_id"],
                attack_method=arguments["attack_method"],
            )
        if name == "delete_target":
            return game.delete_target(target_id=arguments["target_id"])
        if name == "delete_dragon_spot":
            return game.delete_dragon_spot(dragon_spot_id=arguments["dragon_spot_id"])
        return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error: {e}"


def _process_ptt_audio(
    game: GameMap,
    client,
    model: str,
    root,
    transcription_widget,
    llm_widget,
    state_widget,
) -> None:
    """Run in background: stop recording, transcribe, update transcription box, then LLM, then update LLM and state."""
    raw = stop_ptt_recording()
    if not raw:
        root.after(0, lambda: _set_text(transcription_widget, "(no audio)"))
        return

    # 1) Transcribe and show in transcription box first
    text = transcribe_audio_bytes(raw)
    root.after(0, lambda: _set_text(transcription_widget, text or "(empty transcription)"))

    if not text or text == "(empty transcription)":
        root.after(0, lambda: _set_text(llm_widget, "(skipped — no speech to send)"))
        root.after(0, lambda: _set_text(state_widget, format_state_string(game)))
        return

    # 2) LLM and tools (include current state so model uses real ids, not hallucinations)
    llm_display: list[str] = []
    state_context = format_state_for_llm(game.snapshot())
    try:
        response = chat_with_tools(
            client=client,
            user_text=text,
            model=model,
            system_prompt=SYSTEM_PROMPT,
            state_context=state_context,
        )
    except Exception as e:
        root.after(0, lambda: _set_text(llm_widget, f"Error: {e}"))
        root.after(0, lambda: _set_text(state_widget, format_state_string(game)))
        return

    msg = response.choices[0].message if response.choices else None
    if not msg:
        root.after(0, lambda: _set_text(llm_widget, "(empty LLM response)"))
        root.after(0, lambda: _set_text(state_widget, format_state_string(game)))
        return

    tool_calls = getattr(msg, "tool_calls", None) or []
    if tool_calls:
        for tc in tool_calls:
            name = tc.function.name if hasattr(tc.function, "name") else tc.get("function", {}).get("name")
            raw_args = tc.function.arguments if hasattr(tc.function, "arguments") else tc.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {}
            result = execute_tool(game, name, args)
            llm_display.append(f"Tool: {name}({args})\nResult: {result}")
    else:
        content = getattr(msg, "content", None) or ""
        llm_display.append(content.strip() or "(no content)")

    result_text = "\n\n".join(llm_display)
    state_text = format_state_string(game)
    root.after(0, lambda: _set_text(llm_widget, result_text))
    root.after(0, lambda: _set_text(state_widget, state_text))


def _set_text(widget, text: str) -> None:
    widget.delete("1.0", "end")
    widget.insert("1.0", text)


def run_ptt_ui(game: GameMap, client, model: str) -> None:
    import tkinter as tk
    root = tk.Tk()
    root.title("Voice Game Map — Push to talk")
    root.geometry("720x680")
    root.minsize(400, 400)

    # Top: instructions and PTT button
    frame_top = tk.Frame(root, padx=8, pady=8)
    frame_top.pack(fill=tk.X)
    tk.Label(frame_top, text="Hold the button (or Space) to record. Release to transcribe and send.", font=("Segoe UI", 9)).pack(anchor=tk.W)
    ptt_btn = tk.Button(
        frame_top,
        text="Hold to talk",
        font=("Segoe UI", 14, "bold"),
        bg="#2d7d46",
        fg="white",
        activebackground="#1e5c32",
        activeforeground="white",
        relief=tk.RAISED,
        padx=24,
        pady=12,
        cursor="hand2",
    )
    ptt_btn.pack(pady=8)

    # Transcription (filled first after you release PTT)
    frame_trans = tk.Frame(root, padx=8, pady=4)
    frame_trans.pack(fill=tk.BOTH, expand=False)
    tk.Label(frame_trans, text="Transcription (what was heard):", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
    trans_text = tk.Text(frame_trans, height=3, wrap=tk.WORD, font=("Segoe UI", 11), state=tk.NORMAL)
    trans_text.pack(fill=tk.X, pady=(0, 8))

    # LLM response (filled after transcription)
    frame_llm = tk.Frame(root, padx=8, pady=4)
    frame_llm.pack(fill=tk.BOTH, expand=False)
    tk.Label(frame_llm, text="LLM response / actions:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
    llm_text = tk.Text(frame_llm, height=5, wrap=tk.WORD, font=("Segoe UI", 11), state=tk.NORMAL)
    llm_text.pack(fill=tk.X, pady=(0, 8))

    # Game state
    frame_state = tk.Frame(root, padx=8, pady=4)
    frame_state.pack(fill=tk.BOTH, expand=True)
    tk.Label(frame_state, text="Game state:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
    state_text = tk.Text(frame_state, wrap=tk.WORD, font=("Consolas", 10), state=tk.NORMAL)
    state_text.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
    _set_text(state_text, format_state_string(game))

    processing = {"value": False}

    def on_ptt_start(event=None) -> None:
        if processing["value"]:
            return
        start_ptt_recording()
        ptt_btn.config(text="Recording...", bg="#c62828", activebackground="#b71c1c")

    def on_ptt_stop(event=None) -> None:
        ptt_btn.config(text="Hold to talk", bg="#2d7d46", activebackground="#1e5c32")
        if processing["value"]:
            return
        processing["value"] = True
        ptt_btn.config(state=tk.DISABLED)
        trans_text.delete("1.0", "end")
        trans_text.insert("1.0", "Transcribing...")
        llm_text.delete("1.0", "end")
        llm_text.insert("1.0", "Waiting for LLM...")

        def work() -> None:
            _process_ptt_audio(game, client, model, root, trans_text, llm_text, state_text)
            root.after(0, lambda: _reenable_ptt())

        def _reenable_ptt() -> None:
            processing["value"] = False
            ptt_btn.config(state=tk.NORMAL)

        threading.Thread(target=work, daemon=True).start()

    def _on_key_press(e) -> None:
        if e.keysym == "space":
            on_ptt_start()
            return "break"

    def _on_key_release(e) -> None:
        if e.keysym == "space":
            on_ptt_stop()
            return "break"

    ptt_btn.bind("<ButtonPress-1>", on_ptt_start)
    ptt_btn.bind("<ButtonRelease-1>", lambda e: on_ptt_stop())
    root.bind("<KeyPress-space>", _on_key_press)
    root.bind("<KeyRelease-space>", _on_key_release)
    root.bind_class("Text", "<KeyPress-space>", _on_key_press)
    root.bind_class("Text", "<KeyRelease-space>", _on_key_release)
    root.focus_set()

    root.mainloop()


def main() -> None:
    base_url = os.environ.get("LM_STUDIO_BASE_URL", DEFAULT_BASE_URL)
    model = os.environ.get("LM_STUDIO_MODEL", DEFAULT_MODEL)

    game = GameMap()
    game.add_knight("Sir Roland", "Castle")
    client = create_client(base_url=base_url)

    run_ptt_ui(game, client, model)


if __name__ == "__main__":
    import sys
    if "--api" in sys.argv:
        import uvicorn
        uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
    else:
        main()
