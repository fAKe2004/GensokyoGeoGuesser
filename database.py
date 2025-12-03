from typing import Iterable, Dict, Optional, List, Callable
import os

from defs import *

# hyperparameters for database paths

loc_sheet_path = "data/locations.csv" # format: loc, lat, lon (no header)
que_sheet_path = "data/questions.csv" # format: global_id, image_filename, loc, category (no header)

que_image_dir = "images/"

# global, shared datasets (room-independent)
# loc -> (lat, lon)
loc_db: Dict[Loc, Coord] = {}

# global index -> Question (shared catalogue)
que_db: Dict[int, Question] = {}

# Per-room runtime state (ephemeral)
from pydantic import BaseModel

class RoomState(BaseModel):
    # sampler
    category_sampler: Optional[Iterable[Category]] = None
    question_sampler: Iterable[int] = iter([])
    dmg_mult_selector: Callable[[int], float] = lambda idx: 1.0
    
    # persistent history
    que_history: List[int] = []
    round_index: int = -1
    team_hp: Dict[Team, float] = {Team.BLUE: max_hp, Team.RED: max_hp}
    
    # round state
    team_coord: Dict[Team, Optional[Coord]] = {Team.BLUE: None, Team.RED: None}
    
    team_answered: Dict[Team, bool] = {Team.BLUE: False, Team.RED: False}
    team_ready_next: Dict[Team, bool] = {Team.BLUE: False, Team.RED: False}
    
    # track if damage has been applied for the current round to avoid double-subtraction
    last_damage_applied_round: Optional[int] = None

    @property
    def answer_revealed(self) -> bool:
        return all(self.team_answered.values())
    
    def force_answer_reveal(self) -> None:
        for team in self.team_answered:
            self.team_answered[team] = True
    
    def init_sampler(self, seed: int):
        self.category_sampler = get_category_sampler(seed)
        self.question_sampler = get_question_sampler(seed)
        self.dmg_mult_selector = get_dmg_mult_selector(seed)
    
    def reset_round_status(self) -> None:
        self.team_coord = {Team.BLUE: None, Team.RED: None}
        self.team_answered = {Team.BLUE: False, Team.RED: False}
        self.team_ready_next = {Team.BLUE: False, Team.RED: False}
        self.last_damage_applied_round = None

# rooms registry
rooms: Dict[str, RoomState] = {}

def get_room(room_id: str) -> RoomState:
    if room_id not in rooms:
        rooms[room_id] = RoomState()
    return rooms[room_id]

def sample_question(room_id: str) -> Question:
    # two mode:
    # 1. if category_sampler is provided, question_sampler is just rng for choosing one from valid questions. 
    # 2. if category_sampler is None, question_sampler must provide non-repeating global indices (i.e., select a series of questions directly)
    
    # in either case, any iterable raises StopIteration will terminate the sampling process.
    try:
        room = get_room(room_id)
        if room.category_sampler is not None:
            cat = next(room.category_sampler)
            valid_ques = [idx for idx, q in que_db.items() if q.category == cat and idx not in room.que_history]
            if not valid_ques:
                raise RuntimeError(f"No more valid questions available for category {cat}.")
            if room.question_sampler is None:
                raise RuntimeError("question_sampler is not configured for this room.")
            idx = next(room.question_sampler) % len(valid_ques)
            idx = valid_ques[idx]
            room.que_history.append(idx)
            return que_db[idx]
        else:
            if room.question_sampler is None:
                raise RuntimeError("question_sampler is not configured for this room.")
            idx = next(room.question_sampler)
            if idx in room.que_history:
                raise RuntimeError(f"Question index {idx} has already been used.")
            elif idx not in que_db:
                raise RuntimeError(f"Question index {idx} is out of bounds.")
            room.que_history.append(idx)
            return que_db[idx]

    except StopIteration:
        raise StopIteration
        # raise RuntimeError("Category selector or question sampler is exhausted.")

# get question at specific history index
# if the index is out of current history range, sample more questions until reaching that index
def get_question_at(target_index: int, room_id: str) -> Question:
    assert 0 <= target_index < max_rounds, f"Target index {target_index} out of bounds."
    room = get_room(room_id)
    while len(room.que_history) <= target_index:
        try:
            sample_question(room_id)
        except StopIteration:
            raise RuntimeError("No more questions can be sampled despite the target index is smaller than max_rounds. Check the samplers.")
    room.round_index = target_index
    return que_db[room.que_history[target_index]]

def get_current_question(room_id: str) -> Question:
    return get_question_at(get_current_round(room_id), room_id)

def get_current_round(room_id: str) -> int:
    return get_room(room_id).round_index

def set_current_round(target_index: int, room_id: str):
    get_question_at(target_index, room_id)
    
def has_next_round(room_id: str) -> bool:
    return get_room(room_id).round_index + 1 < max_rounds

def has_prev_round(room_id: str) -> bool:
    return get_room(room_id).round_index - 1 >= 0
    
def get_dmg_mult(room_id: str) -> float:
    room = get_room(room_id)
    if room.dmg_mult_selector is None:
        raise RuntimeError("dmg_mult_selector is not configured for this room.")
    return room.dmg_mult_selector(get_room(room_id).round_index)

def get_team_hp(team: Team, room_id: str) -> float:
    return get_room(room_id).team_hp[team]

def set_team_hp(team: Team, hp: float, room_id: str):
    get_room(room_id).team_hp[team] = hp
    
def get_team_coord(team: Team, room_id: str) -> Optional[Coord]:
    return get_room(room_id).team_coord[team]

def set_team_coord(team: Team, coord: Optional[Coord], room_id: str):
    get_room(room_id).team_coord[team] = coord

# Deprecated: selected team is session-specific; no per-room selected team state

def set_team_answered(team: Team, answered: bool, room_id: str) -> None:
    get_room(room_id).team_answered[team] = answered

def reset_round_status(room_id: str) -> None:
    get_room(room_id).reset_round_status()

def get_answer_revealed(room_id: str) -> bool:
    return get_room(room_id).answer_revealed

def set_team_ready_next(team: Team, ready: bool, room_id: str) -> None:
    get_room(room_id).team_ready_next[team] = ready

def both_ready_next(room_id: str) -> bool:
    room = get_room(room_id)
    return all(room.team_ready_next.values())

def init_database():    
    # load loc_db
    with open(loc_sheet_path, "r", encoding="utf-8") as loc_file:
        for line in loc_file:
            line = line.strip()
            if not line:
                continue
            loc, lat_str, lon_str = line.split(",")
            lat, lon = float(lat_str), float(lon_str)
            loc_db[loc] = (lat, lon)
    
    # load que_db (supports 4 or 5 columns: id, image_filename, loc, category[, comment])
    with open(que_sheet_path, "r", encoding="utf-8") as que_file:
        for line in que_file:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 4:
                # malformed row, skip
                print(f"[WARN] questions.csv row has <4 columns and will be skipped: {line}")
                continue
            id_str, image_filename, loc, category = parts[:4]
            comment = parts[4] if len(parts) >= 5 else None
            image_path = os.path.join(que_image_dir, image_filename)
            q = Question(image_path=image_path, location=loc, category=category, comment=comment)
            que_db[int(id_str)] = q

    # Do not create/reset any default room here; rooms are created via init_room

def init_room(room_id: str):
    # Initialize a new room with its own samplers and selectors
    if room_id in rooms:
        pass
    else:
        rooms[room_id] = RoomState()
        rooms[room_id].init_sampler(seed=sum(ord(c) for c in room_id))
    set_current_round(0, room_id)