import database as db
from defs import *

def distance(xy1: Coord, xy2: Coord) -> float:
    # Euclidean distance
    x1, y1 = xy1
    x2, y2 = xy2
    return ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5

def compute_damage(xy1: Coord, xy2: Coord, room_id: int) -> float:
    dist = distance(xy1, xy2) * distance_scale
    damage = dist * db.get_dmg_mult(room_id)
    return damage

