from typing import Iterable, Dict, Optional, List
import os

from defs import *

# hyperparameters for database paths

loc_sheet_path = "data/locations.csv" # format: loc, lat, lon (no header)
que_sheet_path = "data/questions.csv" # format: global_id, image_filename, loc, category (no header)

que_image_dir = "images/"

# global variables for database operations

# loc -> (lat, lon)
loc_db: Dict[Loc, Coord] = {}

# global index -> Question
que_db: Dict[int, Question] = {}

# history of asked questions
que_history: List[int] = []
round_index: int = -1

# sampler
category_sampler: Optional[Iterable[Category]]
question_sampler: Iterable[int]
dmg_mult_selector: Callable[[int], float]

# team specific
team_hp: Dict[Team, float] = {Team.BLUE: max_hp, Team.RED: max_hp}
team_coord: Dict[Team, Optional[Coord]] = {Team.BLUE: None, Team.RED: None}

def sample_question(category_sampler: Optional[Iterable[Category]], question_sampler: Iterable[int]) -> Question:
    # two mode:
    # 1. if category_sampler is provided, question_sampler is just rng for choosing one from valid questions. 
    # 2. if category_sampler is None, question_sampler must provide non-repeating global indices (i.e., select a series of questions directly)
    
    # in either case, any iterable raises StopIteration will terminate the sampling process.
    try:
        if category_sampler is not None:
            cat = next(category_sampler)
            valid_ques = [idx for idx, q in que_db.items() if q.category == cat and idx not in que_history]
            if not valid_ques:
                raise RuntimeError(f"No more valid questions available for category {cat}.")
            idx = next(question_sampler) % len(valid_ques)
            idx = valid_ques[idx]
            que_history.append(idx)
            return que_db[idx]
        else:
            idx = next(question_sampler)
            if idx in que_history:
                raise RuntimeError(f"Question index {idx} has already been used.")
            elif idx not in que_db:
                raise RuntimeError(f"Question index {idx} is out of bounds.")
            que_history.append(idx)
            return que_db[idx]

    except StopIteration:
        raise StopIteration
        # raise RuntimeError("Category selector or question sampler is exhausted.")

# get question at specific history index
# if the index is out of current history range, sample more questions until reaching that index
def get_question_at(target_index: int) -> Question:
    assert 0 <= target_index < max_rounds, f"Target index {target_index} out of bounds."
    while len(que_history) <= target_index:
        try:
            sample_question(category_sampler, question_sampler)
        except StopIteration:
            raise RuntimeError("No more questions can be sampled despite the target index is smaller than max_rounds. Check the samplers.")
        
    global round_index
    round_index = target_index
    return que_db[que_history[target_index]]

def get_current_question() -> Question:
    return get_question_at(round_index)

def get_current_round() -> int:
    return round_index

def set_current_round(target_index: int):
    get_question_at(target_index)
    
def has_next_round() -> bool:
    return round_index + 1 < max_rounds

def has_prev_round() -> bool:
    return round_index - 1 >= 0
    
def get_dmg_mult() -> float:
    return dmg_mult_selector(round_index)

def get_team_hp(team: Team) -> float:
    return team_hp[team]

def set_team_hp(team: Team, hp: float):
    team_hp[team] = hp
    
def get_team_coord(team: Team) -> Optional[Coord]:
    return team_coord[team]

def set_team_coord(team: Team, coord: Coord):
    team_coord[team] = coord

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

    global round_index, que_history
    round_index = -1
    que_history = []
    
    global category_sampler, question_sampler, dmg_mult_selector
    category_sampler = get_category_sampler()
    question_sampler = get_question_sampler()
    dmg_mult_selector = get_dmg_mult_selector()
    
    global team_hp
    team_hp = {Team.BLUE: max_hp, Team.RED: max_hp}
    
    global team_coord
    team_coord = {Team.BLUE: None, Team.RED: None}
    
    set_current_round(0)