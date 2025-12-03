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
max_rounds = 20
max_hp = 100.0

place_guess_timeout = 60 # in seconds
agree_next_timeout = 6 # in seconds

# remark: the internal coordinate system normalizes to [0, 1]
distance_scale = 100


def get_category_sampler(seed: int) -> Sampler[Category]:
    categories = ["E"] * 10 + ["M"] * 5 + ["H"] * 2
    return iter(categories)
    
def get_question_sampler(seed: int) -> Sampler:
    import random
    def sampler():
        while True:
            yield random.randint(0, 1000000)
    return sampler()

def get_dmg_mult_selector(seed: int) -> Callable[[int], float]:
    dmg_mults = [1.0] * 10 + [2.5] * 5 + [4.0] * 2
    return lambda idx: dmg_mults[idx % len(dmg_mults)]