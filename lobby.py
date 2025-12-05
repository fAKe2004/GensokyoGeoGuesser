import threading
import time
import uuid
from enum import Enum
from typing import Optional, Tuple, List, Dict

import database as db
from defs import Team

class RoomStatus(Enum):
    EMPTY = "empty"
    MATCHING = "matching"
    IN_GAME = "in_game"
    ENDED = "ended"

# Tracks lobby room statuses
room_status: dict[str, RoomStatus] = {}

# Queues
# Quick match: list of channel_ids
quick_match_queue: List[str] = []
# Room match: room_id -> list of channel_ids
room_queues: Dict[str, List[str]] = {}

# Match results: channel_id -> {room_id, team}
# Used to pass info back to the request that triggered the match
match_results: Dict[str, dict] = {}

# Last seen timestamp for channels (for pruning)
channel_last_seen: dict[str, float] = {}

lobby_lock = threading.Lock()

# Pruning state
last_prune_time = 0.0
PRUNE_INTERVAL = 5.0  # Run pruning at most every 5 seconds

def lobby_lock_guard(func):
    def wrapper(*args, **kwargs):
        with lobby_lock:
            return func(*args, **kwargs)
    return wrapper

def get_room_status(room_id: str) -> RoomStatus:
    return room_status.get(room_id, RoomStatus.EMPTY)

def set_room_status(room_id: str, status: RoomStatus) -> None:
    room_status[room_id] = status

def mark_channel_seen(channel_id: str) -> None:
    channel_last_seen[channel_id] = time.time()

def _prune_stale_waiters_internal(timeout_sec: float = 15) -> None:
    now = time.time()
    
    # Quick match queue
    global quick_match_queue
    valid_q = []
    for ch in quick_match_queue:
        last = channel_last_seen.get(ch, now)
        if now - last <= timeout_sec:
            valid_q.append(ch)
    quick_match_queue = valid_q
    
    # Room queues
    for room_id, q in list(room_queues.items()):
        valid_room_q = []
        for ch in q:
            last = channel_last_seen.get(ch, now)
            if now - last <= timeout_sec:
                valid_room_q.append(ch)
        room_queues[room_id] = valid_room_q
        if not valid_room_q:
            del room_queues[room_id]

    # Cleanup channel_last_seen for very old entries
    cleanup_threshold = 120.0 # 2 minutes
    to_remove = []
    for ch, last in channel_last_seen.items():
        if now - last > cleanup_threshold:
            to_remove.append(ch)
    
    for ch in to_remove:
        channel_last_seen.pop(ch, None)
        match_results.pop(ch, None)

def prune_stale_rooms() -> None:
    """Destroy rooms that have been marked ENDED."""
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

def _perform_matching():
    # 1. Quick Match
    while len(quick_match_queue) >= 2:
        p1 = quick_match_queue.pop(0)
        p2 = quick_match_queue.pop(0)
        
        new_room = f"room_{uuid.uuid4().hex}"
        set_room_status(new_room, RoomStatus.IN_GAME)
        if new_room not in db.rooms:
            db.init_room(new_room)
            db.reset_round_status(new_room)
            
        match_results[p1] = {"room": new_room, "team": Team.BLUE}
        match_results[p2] = {"room": new_room, "team": Team.RED}

    # 2. Room Match
    for room_id, q in list(room_queues.items()):
        if len(q) >= 2:
            p1 = q.pop(0)
            p2 = q.pop(0)
            
            set_room_status(room_id, RoomStatus.IN_GAME)
            if room_id not in db.rooms:
                db.init_room(room_id)
                db.reset_round_status(room_id)
            
            match_results[p1] = {"room": room_id, "team": Team.BLUE}
            match_results[p2] = {"room": room_id, "team": Team.RED}
            
            # Clean up empty queue
            if not q:
                del room_queues[room_id]

@lobby_lock_guard
def join_match(optional_room_id: Optional[str]) -> Tuple[Optional[str], str, Optional[Team], Optional[str]]:
    """Unified join logic.
    Returns (room_id, channel_id, assigned_team, error_message).
    """
    global last_prune_time
    now = time.time()
    if now - last_prune_time > PRUNE_INTERVAL:
        _prune_stale_waiters_internal()
        prune_stale_rooms()
        last_prune_time = now
    
    my_channel_id = f"wait:{uuid.uuid4().hex}"
    mark_channel_seen(my_channel_id)
    
    if optional_room_id:
        room_id = optional_room_id
        status = get_room_status(room_id)
        if status == RoomStatus.IN_GAME:
            return None, my_channel_id, None, "Room already in game. Please choose another room."
        
        if room_id not in room_queues:
            room_queues[room_id] = []
        room_queues[room_id].append(my_channel_id)
        set_room_status(room_id, RoomStatus.MATCHING)
    else:
        quick_match_queue.append(my_channel_id)
        
    _perform_matching()
    
    # Check if I was matched immediately
    if my_channel_id in match_results:
        res = match_results.pop(my_channel_id)
        return res["room"], my_channel_id, res["team"], None
    else:
        # Still waiting
        return None, my_channel_id, Team.BLUE, None

@lobby_lock_guard
def check_match_status(channel_id: str) -> Tuple[Optional[str], Optional[Team]]:
    mark_channel_seen(channel_id)
    if channel_id in match_results:
        res = match_results.pop(channel_id)
        return res["room"], res["team"]
    return None, None

@lobby_lock_guard
def cancel_waiting(channel_id: str) -> None:
    if channel_id in quick_match_queue:
        quick_match_queue.remove(channel_id)
    
    for room_id, q in list(room_queues.items()):
        if channel_id in q:
            q.remove(channel_id)
            if not q:
                del room_queues[room_id]
                set_room_status(room_id, RoomStatus.EMPTY)
    
    channel_last_seen.pop(channel_id, None)
    match_results.pop(channel_id, None)

@lobby_lock_guard
def mark_stale_room(room_id: str):
    room_status[room_id] = RoomStatus.ENDED