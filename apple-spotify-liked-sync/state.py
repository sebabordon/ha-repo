import json
import os

CONFIG_DIR = os.path.expanduser("~/.apple_spotify_sync")
STATE_PATH = os.path.join(CONFIG_DIR, "state.json")

EMPTY_STATE = {
    # norm_key -> {"spotify_id": str|None, "apple_id": str|None, "name": str, "artist": str}
    "matches": {},
    "spotify_liked_ids": [],
    "apple_loved_ids": [],
}


def load_state():
    if not os.path.exists(STATE_PATH):
        return None
    with open(STATE_PATH) as f:
        return json.load(f)


def save_state(state):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
