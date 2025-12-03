from flask import Flask, jsonify, request, send_from_directory, redirect
import os

import database as db
import calc
from defs import *

app = Flask(__name__, static_folder="static", static_url_path="")

# Global debug flag (can be enabled via command-line arg or environment)
DEBUG_MODE: bool = False

def reveal_damage(room_id: str, state: dict):
    for team in [Team.BLUE, Team.RED]:
        team_coord = db.get_team_coord(team, room_id)
        # if coord missing (e.g., refresh), treat as default midpoint
        if team_coord is None:
            db.set_team_coord(team, (0.5, 0.5), room_id)
        
    damage = {}
    for team in [Team.BLUE, Team.RED]:
        team_coord = db.get_team_coord(team, room_id)
        ans_coord = state.get("answer_coord")
        dmg = calc.compute_damage(team_coord, ans_coord, room_id)
        damage[team.value.lower()] = dmg
        current_hp = db.get_team_hp(team, room_id)
        db.set_team_hp(team, current_hp - dmg, room_id)
    
    state["damage"] = damage
    state["hp"]["blue"] = db.get_team_hp(Team.BLUE, room_id)
    state["hp"]["red"] = db.get_team_hp(Team.RED, room_id)


@app.route("/")
def index():
    room_id = request.args.get("room")
    if not room_id:
        return redirect("/lobby")
    return send_from_directory(app.static_folder, "index.html")

@app.route("/api/state")
def get_state():
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400
    if db.get_current_round(room_id) < 0:
        try:
            db.set_current_round(0, room_id)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500

    try:
        question = db.get_current_question(room_id)
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
        "round": db.get_current_round(room_id),
        "dmg_mult": db.get_dmg_mult(room_id),
        "question_comment": question.comment,
        "hp": {
            "blue": db.get_team_hp(Team.BLUE, room_id),
            "red": db.get_team_hp(Team.RED, room_id),
        },
        "question_img": image_path,
        "answer_coord": answer_coord,
        "answer_loc": answer_loc,
        "answer_revealed": db.get_answer_revealed(room_id),
        "debug": DEBUG_MODE,
        "coords": {
            "blue": db.get_team_coord(Team.BLUE, room_id),
            "red": db.get_team_coord(Team.RED, room_id),
        },
        "has_next": db.has_next_round(room_id),
        "has_prev": db.has_prev_round(room_id),
        "selected_team": db.get_selected_team(room_id).value,
    }
    # If answer has been revealed earlier, include damage on state fetch so refresh shows it
    if state["answer_revealed"]:
        reveal_damage(room_id, state)
    return jsonify(state)

@app.route("/lobby")
def lobby():
    # Serve the simple lobby page for choosing a room and team
    return send_from_directory(app.static_folder, "lobby.html")

@app.route("/api/next_round", methods=["POST"])
def next_round():
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400
    if db.has_next_round(room_id):
        db.set_current_round(db.get_current_round(room_id) + 1, room_id)
    print("ACTION: Next Round")
    print("> question ", db.get_current_question(room_id))

    db.reset_round_status(room_id)

    return get_state()

@app.route("/api/prev_round", methods=["POST"])
def prev_round():
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400
    if db.has_prev_round(room_id):
        db.set_current_round(db.get_current_round(room_id) - 1, room_id)
    print("ACTION: Prev Round")
    print("> question ", db.get_current_question(room_id))

    db.reset_round_status(room_id)

    return get_state()

@app.route("/api/select_team", methods=["POST"])
def select_team():
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400
    team_str = request.json.get("team")
    if not team_str:
        return jsonify({"error": "Team not specified"}), 400
        
    try:
        team = Team(team_str.capitalize())
        db.set_selected_team(team, room_id)
        print(f"ACTION: Selected team {team} in room {room_id}")
    except ValueError:
        return jsonify({"error": "Invalid team"}), 400
    return get_state()

@app.route("/api/place_guess", methods=["POST"])
def place_guess():
    data = request.json
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400
    coord = (data.get("lat"), data.get("lon"))
    team = db.get_selected_team(room_id)
    db.set_team_coord(team, coord, room_id)
    print(f"ACTION: Placed guess for team {team} in room {room_id} at ({coord[0]:.2f}, {coord[1]:.2f})")
    return get_state()

@app.route("/api/reveal", methods=["GET"])
def reveal():
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400

    db.rooms.get(room_id).force_answer_reveal()

    return get_state()

@app.route("/api/init", methods=["POST"])
def init_game():
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400
    # initialize shared datasets (idempotent) and ensure room exists
    if not db.loc_db or not db.que_db:
        db.init_database()
    db.init_room(room_id)
    db.reset_round_status(room_id)
    return get_state()


if __name__ == "__main__":
    import sys, os
    db.init_database()
    # Enable DEBUG_MODE if '--debug' arg provided or ENV DEBUG=true
    DEBUG_MODE = ("--debug" in sys.argv) or (str(os.environ.get("DEBUG", "")).lower() in {"1","true","yes"})
    print(f"DEBUG_MODE = {DEBUG_MODE}")
    app.run(debug=True, port=5000)
