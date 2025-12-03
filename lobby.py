import queue
import threading
from time import time
import uuid
from enum import Enum
from typing import Optional, Tuple

import database as db
from defs import Team

class RoomStatus(Enum):
    EMPTY = "empty"
    MATCHING = "matching"
    IN_GAME = "in_game"
    ENDED = "ended"

# Tracks lobby room statuses
room_status: dict[str, RoomStatus] = {}

"""Lobby matchmaking primitives.
- If a specific room_id is provided: first joiner waits (BLUE), second joiner matches (RED) and room enters IN_GAME.
- If no room_id is provided: use a global quick-match queue; first waits (BLUE), second matches (RED) and a new room is created.
"""

# Single waiting player channel for global quick match (no room chosen)
waiting_global_channel: Optional[str] = None

# Per-room waiting channel ids (first joiner waiting)
waiting_per_room_channel: dict[str, Optional[str]] = {}

# Lobby SSE channels: arbitrary channel id -> list of queues
lobby_event_channels: dict[str, list[queue.Queue]] = {}
channel_last_seen: dict[str, float] = {}

lobby_lock = threading.Lock()

def lobby_lock_guard(func):
    def wrapper(*args, **kwargs):
        with lobby_lock:
            return func(*args, **kwargs)
    return wrapper

def get_room_status(room_id: str) -> RoomStatus:
    return room_status.get(room_id, RoomStatus.EMPTY)

def set_room_status(room_id: str, status: RoomStatus) -> None:
    room_status[room_id] = status

def _broadcast_lobby(channel_id: str, msg: str) -> None:
    for q in lobby_event_channels.get(channel_id, []):
        try:
            q.put(msg)
        except Exception:
            pass

def create_lobby_event_stream(channel_id: str) -> queue.Queue:
    q: queue.Queue[str] = queue.Queue()
    lobby_event_channels.setdefault(channel_id, []).append(q)
    # Mark channel seen at subscription time
    try:
        import time
        channel_last_seen[channel_id] = time.time()
    except Exception:
        pass
    return q

def mark_channel_seen(channel_id: str) -> None:
    try:
        import time
        channel_last_seen[channel_id] = time.time()
    except Exception:
        pass

def prune_stale_waiters(timeout_sec: float = 2) -> None:
    # timeout at HTML side is 1 second
    """Remove waiting channels if they haven't pinged recently."""
    try:
        import time
        now = time.time()
        # Global
        global waiting_global_channel
        if waiting_global_channel:
            last = channel_last_seen.get(waiting_global_channel, 0)
            if now - last > timeout_sec:
                waiting_global_channel = None
        # Per-room
        to_clear: list[str] = []
        for room_id, chan in waiting_per_room_channel.items():
            if not chan:
                continue
            last = channel_last_seen.get(chan, 0)
            if now - last > timeout_sec:
                to_clear.append(room_id)
        for room_id in to_clear:
            waiting_per_room_channel[room_id] = None
    except Exception:
        pass

def prune_stale_rooms() -> None:
    """Destroy rooms that have been marked ENDED for more than 10 seconds."""
    try:
        to_destroy: list[str] = [
            room_id for room_id, status in room_status.items()
            if status == RoomStatus.ENDED
        ]
        for room_id in to_destroy:
            room_status.pop(room_id, None)
            db.rooms.pop(room_id, None)
    except Exception:
        pass

@lobby_lock_guard
def join_match(optional_room_id: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[Team], Optional[str]]:
    """Unified join logic.
    Returns (room_id, sse_channel, assigned_team, error_message).
    - If error_message is not None, the join failed and should be reported.
    - If room_id is None, caller should wait on SSE channel for 'matched:<room>:<team>'.
    - If room_id is set, caller is immediately matched and can proceed.
    """
    prune_stale_waiters()
    prune_stale_rooms()
    
    if optional_room_id:
        room_id = optional_room_id
        status = get_room_status(room_id)
        if status == RoomStatus.IN_GAME:
            return None, None, None, "Room already in game. Please choose another room."
        if status in (RoomStatus.EMPTY, RoomStatus.MATCHING):
            # First joiner: set to MATCHING and wait as BLUE using a dedicated channel
            set_room_status(room_id, RoomStatus.MATCHING)
            channel = waiting_per_room_channel.get(room_id)
            if channel:
                # Second joiner matches now
                set_room_status(room_id, RoomStatus.IN_GAME)
                waiting_per_room_channel[room_id] = None
                # Initialize room if needed
                if room_id not in db.rooms:
                    db.init_room(room_id)
                    db.reset_round_status(room_id)
                _broadcast_lobby(channel, f"matched:{room_id}:blue")
                return room_id, None, Team.RED, None
            else:
                # Create a unique channel for the first joiner
                channel_id = f"roomwait:{room_id}:{uuid.uuid4().hex}"
                waiting_per_room_channel[room_id] = channel_id
                return None, channel_id, Team.BLUE, None
    else:
        # Global quick match
        global waiting_global_channel
        if waiting_global_channel:
            # Match with the waiting player: create a new room
            new_room = f"room_{uuid.uuid4().hex}"
            set_room_status(new_room, RoomStatus.IN_GAME)
            if new_room not in db.rooms:
                db.init_room(new_room)
                db.reset_round_status(new_room)
            _broadcast_lobby(waiting_global_channel, f"matched:{new_room}:blue")
            waiting_global_channel = None
            return new_room, None, Team.RED, None
        else:
            # No one waiting yet: current becomes first joiner (BLUE) and waits on a private channel
            channel_id = f"globalwait:{uuid.uuid4().hex}"
            waiting_global_channel = channel_id
            return None, channel_id, Team.BLUE, None
        
@lobby_lock_guard
def mark_stale_room(room_id: str):
    room_status[room_id] = RoomStatus.ENDED