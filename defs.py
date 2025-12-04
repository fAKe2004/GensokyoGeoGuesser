from typing import Tuple, Iterable, Optional, Callable

from enum import Enum

from pydantic import BaseModel

class Team(str, Enum):
    BLUE = "Blue"
    RED = "Red"

Coord = Tuple[float, float]
Sampler = Iterable
Loc = str
Category = str

class Question(BaseModel):
    image_path: str
    location: Loc
    category: Category
    comment: Optional[str] = None
    
# Question = Tuple[str, Loc] # image path and location


# hyperparameters
max_rounds = 16
max_hp = 100.0

place_guess_timeout = 30 # in seconds
agree_next_timeout = 10 # in seconds

# remark: the internal coordinate system normalizes to [0, 1]
distance_scale = 100

def get_category_sampler(seed: int) -> Sampler[Category]:
    categories = ["E"] * max_rounds
    return iter(categories)
    
def get_question_sampler(seed: int) -> Sampler:
    import random
    def sampler():
        while True:
            yield random.randint(0, 1000000)
    return sampler()

def get_dmg_mult_selector(seed: int) -> Callable[[int], float]:
    split = [max_rounds // 2, max_rounds // 4]
    dmg_mults = [1.0] * split[0] + [2.0] * split[1] + [4.0] * 10000
    return lambda idx: dmg_mults[idx]