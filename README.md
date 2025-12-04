# Gensokyo Geo-Guesser

Gensokyo Geo-Guesser is a 2-team competitive game where players guess the location of various scenes from Gensokyo on a map. The goal is to be more accurate than the opposing team and deplete their HP to zero.

## Game Rules

### Objective

Two teams, **Blue** and **Red**, compete against each other. The game is won by reducing the opponent's HP to zero. If all rounds are completed before a team is knocked out, the team with the higher remaining HP wins.

### Gameplay Flow

1.  **Guessing Phase**: At the start of each round, both teams are shown an image of a location in Gensokyo. Each team must place a pin on the map to guess where the image was taken.
    *   There is a **30-second timer** for this phase.
    *   If a team fails to place a guess within the time limit, a default guess will be placed for them, and their turn will be submitted automatically.

2.  **Reveal Phase**: Once both teams have submitted their guesses, the correct answer is revealed on the map. Lines are drawn from each team's guess to the correct location.

3.  **Damage Calculation**:
    *   Each team's HP is reduced based on how far their guess was from the actual location. The formula is `Damage = Distance × Multiplier`.
    *   A **Damage Multiplier** is in effect for each round. This multiplier may increase in later rounds, making accuracy even more critical.

4.  **Next Round**: After the damage is dealt, players from both teams must agree to proceed to the next round.
    *   There is a **5-second timer** for this phase. If a player doesn't act, the game will automatically proceed.

### Winning the Game

A team wins if:
- The opposing team's HP drops to 0 or below. (if two teams drop to 0 in the same round, team with more HP remaining wins.)
- The game finishes all rounds, and your team has more HP remaining than the opponent.

A **Draw** if both teams have the same amount of HP when game ends by either final round or HP dropping to 0.

## How to Deploy

This web application is built with a Python Flask backend and a plain HTML/CSS/JavaScript frontend.

We host a publicly-accessible demo on [ggg.arthas.org](https://ggg.arthas.org).  Visit the website to enter lobby, and match a opponent.

### 1. Prerequisites

- Python 3.8 or later
- `pip` for installing packages

### 2. Installation

Clone the repository and install the required Python packages:

```bash
git clone <repository-url>
cd GensokyoGeoGuesser
pip install -r requirements.txt
```

### 3. Running the Server

Start the Flask application with the following command:

```bash
python app.py
```

The server will start on `http://localhost:5000` by default.

For development, you can run the server in debug mode, which provides more detailed information and controls:

```bash
python app.py --debug
```

For a production level deployment, please follow the official guide of Flask and WSGI server.

### 4. Playing the Game

1.  Open a web browser and navigate to `http://localhost:5000`. You will be taken to the lobby.
2.  To play, two players must join a room.
    -   **Quick Match**: Leave the "Room ID" field blank and click "Play". The first player will wait, and the second player to do this will be matched with them in a new room.
    -   **Private Room**: Enter a custom Room ID and click "Play". Share the same Room ID with another player and have them join.
3.  Once matched, the game will begin automatically.

