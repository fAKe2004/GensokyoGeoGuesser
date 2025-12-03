from flask import Flask, jsonify, request, send_from_directory
import os

import database as db
import calc
from defs import *

app = Flask(__name__, static_folder="static", static_url_path="")

# Global variable to store the currently selected team
selected_team: Team = Team.BLUE
answer_revealed: bool = False
# Global debug flag (can be enabled via command-line arg or environment)
DEBUG_MODE: bool = False

def reset_round_status():
    global answer_revealed
    answer_revealed = False
    db.set_team_coord(Team.BLUE, None)
    db.set_team_coord(Team.RED, None)

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/api/state")
def get_state():
    if db.get_current_round() < 0:
        try:
            db.set_current_round(0)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500

    try:
        question = db.get_current_question()
        image_path = question.image_path
        loc = question.location
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    # Always include the answer coordinate and location in the state
    answer_coord = db.loc_db.get(loc)
    if answer_coord is None:
        raise RuntimeError(f"Location '{loc}' not found in loc_db.")
    answer_loc = {
        "name": loc,
        "lat": (answer_coord[0] if answer_coord else None),
        "lon": (answer_coord[1] if answer_coord else None),
    }

    state = {
        "round": db.get_current_round(),
        "dmg_mult": db.get_dmg_mult(),
        "question_comment": question.comment,
        "hp": {
            "blue": db.get_team_hp(Team.BLUE),
            "red": db.get_team_hp(Team.RED),
        },
        "question_img": image_path,
        "answer_coord": answer_coord,
        "answer_loc": answer_loc,
        "answer_revealed": answer_revealed,
        "debug": DEBUG_MODE,
        "coords": {
            "blue": db.get_team_coord(Team.BLUE),
            "red": db.get_team_coord(Team.RED),
        },
        "has_next": db.has_next_round(),
        "has_prev": db.has_prev_round(),
        "selected_team": selected_team.value,
    }
    return jsonify(state)

@app.route("/api/next_round", methods=["POST"])
def next_round():
    if db.has_next_round():
        db.set_current_round(db.get_current_round() + 1)
    print("ACTION: Next Round")
    print("> question ", db.get_current_question())

    reset_round_status()

    return get_state()

@app.route("/api/prev_round", methods=["POST"])
def prev_round():
    if db.has_prev_round():
        db.set_current_round(db.get_current_round() - 1)
    print("ACTION: Prev Round")
    print("> question ", db.get_current_question())

    reset_round_status()

    return get_state()

@app.route("/api/select_team", methods=["POST"])
def select_team():
    global selected_team
    team_str = request.json.get("team")
    if not team_str:
        return jsonify({"error": "Team not specified"}), 400
        
    try:
        selected_team = Team(team_str.capitalize())
        print(f"ACTION: Selected team {selected_team}")
    except ValueError:
        return jsonify({"error": "Invalid team"}), 400
    return get_state()

@app.route("/api/place_guess", methods=["POST"])
def place_guess():
    data = request.json
    coord = (data.get("lat"), data.get("lon"))
    db.set_team_coord(selected_team, coord)
    print(f"ACTION: Placed guess for team {selected_team} at ({coord[0]:.2f}, {coord[1]:.2f})")
    return get_state()

@app.route("/api/reveal", methods=["GET"])
def reveal():
    global answer_revealed
    answer_revealed = True

    # Build base state (includes answer details)
    for team in [Team.BLUE, Team.RED]:
        team_coord = db.get_team_coord(team)
        if team_coord is None:
            db.set_team_coord(team, (0.5, 0.5))

    state = get_state().get_json()
    
    # Calculate damage
    damage = {}
    for team in [Team.BLUE, Team.RED]:
        team_coord = db.get_team_coord(team)
        ans_coord = state.get("answer_coord")
        dmg = calc.compute_damage(team_coord, ans_coord)
        damage[team.value.lower()] = dmg
        current_hp = db.get_team_hp(team)
        db.set_team_hp(team, current_hp - dmg)
    
    state["damage"] = damage
    state["hp"]["blue"] = db.get_team_hp(Team.BLUE)
    state["hp"]["red"] = db.get_team_hp(Team.RED)

    return jsonify(state)

@app.route("/api/init", methods=["POST"])
def init_game():
    db.init_database()
    global selected_team
    global answer_revealed
    selected_team = Team.BLUE
    answer_revealed = False
    return get_state()


if __name__ == "__main__":
    import sys, os
    db.init_database()
    # Enable DEBUG_MODE if '--debug' arg provided or ENV DEBUG=true
    DEBUG_MODE = ("--debug" in sys.argv) or (str(os.environ.get("DEBUG", "")).lower() in {"1","true","yes"})
    print(f"DEBUG_MODE = {DEBUG_MODE}")
    app.run(debug=True, port=5000)
