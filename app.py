from flask import Flask, jsonify, request, send_from_directory, redirect, Response
import os
import queue
import time

import database as db
import calc
from defs import *
import lobby as lb

app = Flask(__name__, static_folder="static", static_url_path="")

# Global debug flag (can be enabled via command-line arg or environment)
DEBUG_MODE: bool = False

def dprint(*args, **kwargs):
    if DEBUG_MODE:
        print(*args, **kwargs)
    else:
        pass
    
def end_game_condition(room_id: str, state: dict):
    blue_hp = db.get_team_hp(Team.BLUE, room_id)
    red_hp = db.get_team_hp(Team.RED, room_id)
    
    has_next_round = db.has_next_round(room_id) 
    
    hp_exhausted = blue_hp <= 0 or red_hp <= 0
    round_exhausted = not has_next_round and not hp_exhausted
    
    # end-game condition
    if hp_exhausted or round_exhausted:
        if abs(blue_hp - red_hp) < 0.1 and (
            (blue_hp <= 0 and red_hp <= 0) or round_exhausted
        ):
            winner = "draw"
        else:
            winner = "red" if blue_hp <= red_hp else "blue"
        state["winner"] = winner
        dprint(f"Game outcome determined: winner is {winner} / {hp_exhausted} / {round_exhausted}")
        lb.mark_stale_room(room_id)
    else:
        pass        

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
    
    state["hp"]["blue"] = db.get_team_hp(Team.BLUE, room_id)
    state["hp"]["red"] = db.get_team_hp(Team.RED, room_id)
    
    # judge end_game_condition
    end_game_condition(room_id, state)

    
    

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

    # Determine current phase (from room state) and compute remaining seconds server-side
    current_phase = 'agree_next' if db.get_answer_revealed(room_id) else 'guess'
    phase_started_at = db.get_phase_started_at(room_id)
    now_sec = time.time()    
    if current_phase == 'guess':
        remaining_seconds = place_guess_timeout - (now_sec - phase_started_at)
    else:
        remaining_seconds = agree_next_timeout - (now_sec - phase_started_at)
    remaining_seconds = max(remaining_seconds, 0)
        

    state = {
        "round": db.get_current_round(room_id) + 1, # to 1-indexed.
        "dmg_mult": db.get_dmg_mult(room_id),
        "total_rounds": max_rounds,
        # Synced countdown: backend phase and remaining seconds to avoid clock skew
        "phase": current_phase,
        "phase_remaining_seconds": max(0, int(remaining_seconds)),
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

@app.route("/lobby/events/<room_id>")
def lobby_events(room_id: str):
    q = lb.create_lobby_event_stream(room_id)
    def stream():
        while True:
            msg = q.get()
            yield f"data: {msg}\n\n"
    return Response(stream(), mimetype="text/event-stream")

@app.route("/api/lobby/quick_match", methods=["POST"])
def lobby_quick_match():
    """Unified quick match / room join endpoint.
    Body may include optional { room: <room_id> }.
    Responses:
    - Error (room in game): 400, { error: "Room already in game. Please choose another room." }
    - Immediate match: { matched: true, room: <id>, team: <blue|red>, channel: <sse_channel> }
    - Waiting: { matched: false, team: <blue>, channel: <sse_channel> }
    """
    payload = request.get_json(silent=True) or {}
    requested_room = payload.get("room")
    room_id, sse_channel, team, err = lb.join_match(requested_room)
    if err:
        return jsonify({"error": err}), 400
    if room_id:
        return jsonify({"matched": True, "room": room_id, "team": team.value.lower(), "channel": sse_channel})
    else:
        return jsonify({"matched": False, "team": team.value.lower(), "channel": sse_channel})

@app.route("/api/lobby/ping", methods=["POST"])
def lobby_ping():
    payload = request.get_json(silent=True) or {}
    channel = payload.get("channel")
    if not channel:
        return jsonify({"error": "Missing channel"}), 400
    lb.mark_channel_seen(channel)
    return jsonify({"ok": True})

@app.route("/api/next_round", methods=["POST"])
def next_round():
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400
    if db.has_next_round(room_id):
        db.set_current_round(db.get_current_round(room_id) + 1, room_id)
    dprint("ACTION: Next Round")
    dprint("> question ", db.get_current_question(room_id))

    db.reset_round_status(room_id)

    return get_state()

@app.route("/api/prev_round", methods=["POST"])
def prev_round():
    room_id = request.args.get("room")
    if not room_id:
        return jsonify({"error": "Missing room id"}), 400
    if db.has_prev_round(room_id):
        db.set_current_round(db.get_current_round(room_id) - 1, room_id)
    dprint("ACTION: Prev Round")
    dprint("> question ", db.get_current_question(room_id))

    db.reset_round_status(room_id)

    return get_state()

# after update, this is handled at html side.
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
    dprint(f"ACTION: Placed guess for team {team} in room {room_id} at ({coord[0]:.2f}, {coord[1]:.2f})")
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

    dprint(f"ACTION: Submitted guess for team {team} in room {room_id}")
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
    if db.get_answer_revealed(room_id) and db.get_both_ready_next(room_id) and db.has_next_round(room_id):
        db.set_current_round(db.get_current_round(room_id) + 1, room_id)
        db.reset_round_status(room_id)

    dprint(f"ACTION: Team {team} agreed to next round in room {room_id}")
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
    app.run(debug=False, port=5000)
