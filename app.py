from flask import Flask, jsonify, request, send_from_directory, redirect
import os
import queue
from flask import Response

import database as db
import calc
from defs import *

app = Flask(__name__, static_folder="static", static_url_path="")

# Global debug flag (can be enabled via command-line arg or environment)
DEBUG_MODE: bool = False

def apply_damage(room_id: str, state: dict):
    dmg_mult = state["dmg_mult"]
    damage = {}
    distance = {}
    for team in [Team.BLUE, Team.RED]:
        coord = db.get_team_coord(team, room_id)
        if coord is not None:
            mult = db.get_dmg_mult(room_id)
            dmg = calc.compute_scaled_damage(coord, state.get("answer_coord"), mult)
            damage[team.value.lower()] = dmg
            distance[team.value.lower()] = (dmg / dmg_mult) if dmg_mult else None
        else:
            damage[team.value.lower()] = None
            distance[team.value.lower()] = None
    state["damage"] = damage
    state["distance"] = distance
    # Apply HP once per round after reveal
    room = db.get_room(room_id)
    if room.last_damage_applied_round != state["round"]:
        # subtract hp for each team based on computed damage
        for team in [Team.BLUE, Team.RED]:
            dmg = damage.get(team.value.lower())
            if dmg is None:
                continue
            current_hp = db.get_team_hp(team, room_id)
            db.set_team_hp(team, current_hp - dmg, room_id)
        room.last_damage_applied_round = state["round"]
    # sync hp values in state after potential update
    state["hp"]["blue"] = db.get_team_hp(Team.BLUE, room_id)
    state["hp"]["red"] = db.get_team_hp(Team.RED, room_id)

# Simple SSE event queues per room
event_queues: dict[str, list[queue.Queue]] = {}

def event_stream(q: "queue.Queue[str]"):
    while True:
        msg = q.get()  # blocking
        yield f"data: {msg}\n\n"

def broadcast(room_id: str, msg: str):
    for q in event_queues.get(room_id, []):
        try:
            q.put(msg)
        except Exception:
            pass

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
        mult = db.get_dmg_mult(room_id)
        dmg = calc.compute_scaled_damage(team_coord, ans_coord, mult)
        damage[team.value.lower()] = dmg
        current_hp = db.get_team_hp(team, room_id)
        db.set_team_hp(team, current_hp - dmg, room_id)
    
    state["damage"] = damage
    state["hp"]["blue"] = db.get_team_hp(Team.BLUE, room_id)
    state["hp"]["red"] = db.get_team_hp(Team.RED, room_id)


@app.route("/")
def index():
    room_id = request.args.get("room")
    team_param = request.args.get("team")
    if not room_id or not team_param:
        return redirect("/lobby")
    return send_from_directory(app.static_folder, "index.html")

@app.route("/api/state")
def get_state():
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400
    # Echo team from query (client-side maintained); validate if provided
    team_param = request.args.get("team")
    team_value = None
    if team_param:
        try:
            team_value = Team(team_param.capitalize()).value.lower()
        except Exception:
            team_value = None
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

    def reveal_coord(revealed, team):
        if revealed:
            return {
                    "blue": db.get_team_coord(Team.BLUE, room_id), 
                    "red": db.get_team_coord(Team.RED, room_id)
                }
        else:
            return {
                "blue": db.get_team_coord(Team.BLUE, room_id) if team == "blue" else None,
                "red": db.get_team_coord(Team.RED, room_id) if team == "red" else None,
            }

    state = {
        "round": db.get_current_round(room_id),
        "dmg_mult": db.get_dmg_mult(room_id),
        "question_comment": question.comment,
        "team": team_value,  # session-specific; client controls selection
        "hp": {
            "blue": db.get_team_hp(Team.BLUE, room_id),
            "red": db.get_team_hp(Team.RED, room_id),
        },
        "question_img": image_path,
        "answer_coord": answer_coord,
        "answer_loc": answer_loc,
        "answer_revealed": db.get_answer_revealed(room_id),
        "debug": DEBUG_MODE,
        # Hide opponent's coords until answer is revealed
        "coords": reveal_coord(db.get_answer_revealed(room_id), team_value),
        "has_next": db.has_next_round(room_id),
        "has_prev": db.has_prev_round(room_id),
        # selected_team is deprecated; team is session-specific (via URL)
        "team_answered": {
            "blue": db.get_room(room_id).team_answered[Team.BLUE],
            "red": db.get_room(room_id).team_answered[Team.RED]
        },
        "team_ready_next": {
            "blue": db.get_room(room_id).team_ready_next[Team.BLUE],
            "red": db.get_room(room_id).team_ready_next[Team.RED]
        }
    }
    # If revealed, compute damage and distance consistently for the payload.
    if state["answer_revealed"]:
        apply_damage(room_id, state)
        
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

# @app.route("/api/select_team", methods=["POST"])
# def select_team():
#     room_id = request.args.get("room")
#     if not room_id:
#         return jsonify({"error": "Missing room id"}), 400
#     team_str = request.json.get("team")
#     if not team_str:
#         return jsonify({"error": "Team not specified"}), 400
        
#     try:
#         team = Team(team_str.capitalize())
#         # Deprecated: selection is session-specific; keep endpoint for admin debug UI only
#         print(f"[DEBUG] Selected team (session): {team} in room {room_id}")
#     except ValueError:
#         return jsonify({"error": "Invalid team"}), 400
#     return get_state()

@app.route("/api/place_guess", methods=["POST"])
def place_guess():
    data = request.json
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400
    coord = (data.get("lat"), data.get("lon"))
    # Allow explicit team via query for per-session separation
    team_param = request.args.get("team")
    if not team_param:
        return jsonify({"error": "Missing team"}), 400
    try:
        team = Team(team_param.capitalize())
    except Exception:
        return jsonify({"error": "Invalid team"}), 400
    # Ignore placing a guess after submission (no-op)
    if db.get_room(room_id).team_answered.get(team):
        return get_state()
    db.set_team_coord(team, coord, room_id)
    print(f"ACTION: Placed guess for team {team} in room {room_id} at ({coord[0]:.2f}, {coord[1]:.2f})")
    return get_state()

@app.route("/api/submit", methods=["POST"])
def submit_guess():
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400
    team_param = request.args.get("team")
    if not team_param:
        return jsonify({"error": "Missing team"}), 400
    try:
        team = Team(team_param.capitalize())
    except Exception:
        return jsonify({"error": "Invalid team"}), 400
    if db.get_team_coord(team, room_id) is None:
        return jsonify({"error": "No guess to submit"}), 400
    db.set_team_answered(team, True, room_id)

    # whenever click, broadcast
    broadcast(room_id, "reveal")
    return get_state()

@app.route("/api/reveal", methods=["GET"])
def reveal():
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400
    # Allow manual reveal (admin/debug). Otherwise, reveal happens when both teams answered.
    if DEBUG_MODE:
        db.rooms.get(room_id).force_answer_reveal()
    else:
        if not all(db.rooms.get(room_id).team_answered.values()):
            return jsonify({"error": "Not ready to reveal"}), 400
    
    # Notify both clients to refresh
    broadcast(room_id, "reveal")

    return get_state()

@app.route("/api/agree_next", methods=["POST"])
def agree_next():
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400
    team_param = request.args.get("team")
    if not team_param:
        return jsonify({"error": "Missing team"}), 400
    try:
        team = Team(team_param.capitalize())
    except Exception:
        return jsonify({"error": "Invalid team"}), 400
    db.set_team_ready_next(team, True, room_id)
    if db.get_answer_revealed(room_id) and db.both_ready_next(room_id) and db.has_next_round(room_id):
        db.set_current_round(db.get_current_round(room_id) + 1, room_id)
        db.reset_round_status(room_id)

    # Notify both clients to refresh
    broadcast(room_id, "next_round")
    return get_state()

@app.route("/events/<room_id>")
def events(room_id: str):
    q: queue.Queue[str] = queue.Queue()
    event_queues.setdefault(room_id, []).append(q)
    return Response(event_stream(q), mimetype="text/event-stream")

@app.route("/api/init", methods=["POST"])
def init_game():
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400
    # initialize shared datasets and ensure room exists
    if not db.loc_db or not db.que_db:
        db.init_database()
    # Only initialize a new room if not present; avoid resetting when a second player joins
    if room_id not in db.rooms:
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
