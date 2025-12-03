import database as db
from defs import *

def distance(xy1: Coord, xy2: Coord) -> float:
    # Euclidean distance
    x1, y1 = xy1
    x2, y2 = xy2
    return ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5

def compute_scaled_distance(xy1: Coord, xy2: Coord) -> float:
    return distance(xy1, xy2) * distance_scale

def compute_scaled_damage(xy1: Coord, xy2: Coord, mult: int) -> float:
    dist = compute_scaled_distance(xy1, xy2)
    damage = dist * mult
    return damage

