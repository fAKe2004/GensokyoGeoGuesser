# Gensokyo Geo-Guesser

This repository contains the Gensokyo Geo Guessor game for SJTU Touhou Festive 2025.

**Try-out**: You may try our deployment demo available at [ggg.arthas.org](https://ggg.arthas.org).


**Description**: Gensokyo Geo-Guesser is a 2-team competitive game where players guess the location of various scenes from Gensokyo on a map. The goal is to be more accurate than the opposing team and deplete their HP to zero.

---
## Credits

- We give special thanks to MC幻想乡 circle for sharing their map.

- 浮云 @ SJTU
	- Project proposal
	- Questions data set construction.
- fAKe @ SJTU
	- Core code design and implement.
    - Online demo deployment.

> For touhou event hosters, you're welcome to adapt this project for your Touhou events. Please credit us as “上海交通大学东方社”. Please also give credit to “MC幻想乡”.

> You don't need our prior permission to use it, though we'd love to hear about your usage.

> You may use our deployment (i.e., [ggg.arthas.org](ggg.arthas.org)) directly if you are not expert in computer science. In that case, we recommand contacting [project owner](mailto:fake@sjtu.edu.cn) beforehand to get potential maintanance support during your Touhou event.



---


## Contact

1. For technical questions (improvements, deployment issues, etc.), email to [fake@sjtu.edu.cn](mailto:fake@sjtu.edu.cn), or open an issue/pull request in this repository.

2. If you adapt this project for your own Touhou event, feel free to let us know by contacting the administrators in any of our club's QQ groups (e.g., `471319153` for vistors).

---

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
    *   There is a **10-second timer** for this phase. If a player doesn't act, the game will automatically proceed.

### Winning the Game

A team wins if:
- The opposing team's HP drops to 0 or below. (if two teams drop to 0 in the same round, team with more HP remaining wins.)
- The game finishes all rounds, and your team has more HP remaining than the opponent.

A **Draw** if both teams have the same amount of HP when game ends by either final round or HP dropping to 0.

## How to Deploy

> You may use our deployment (i.e., [ggg.arthas.org](ggg.arthas.org)) directly if you are not expert in computer science. In that case, we recommand contacting [project maintainer](mailto:fake@sjtu.edu.cn) beforehand to get potential maintanance support during your Touhou event.

This web application is built with a Python Flask backend and a plain HTML/CSS/JavaScript frontend.

We host a publicly-accessible demo on [ggg.arthas.org](https://ggg.arthas.org).  Visit the website to enter lobby, and match a opponent.

### 1. Prerequisites

- Python 3.8 or later
- `pip` for installing packages

### 2. Installation

Clone the repository and install the required Python packages:

```bash
git clone https://github.com/fAKe2004/GensokyoGeoGuesser
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

>hint: you can see the normalized coordintates for your guess in debug model, which is helpful for get loc $\to$ coord mapping when constructing question dataset.




### 4. Playing the Game

1.  Open a web browser and navigate to `http://localhost:5000`. You will be taken to the lobby.
2.  To play, two players must join a room.
    -   **Quick Match**: Leave the "Room ID" field blank and click "Play". The first player will wait, and the second player to do this will be matched with them in a new room.
    -   **Private Room**: Enter a custom Room ID and click "Play". Share the same Room ID with another player and have them join.
3.  Once matched, the game will begin automatically.

### 5. Deploy on an Internet Server

Deploying this game is the same as any other web apps. You may ask AI for 'how to create a service to maintain flask app alive', and 'how to set up reverse proxy to forward traffic to local apps'.

~~For a production level deployment, please follow the official guide of Flask and WSGI server.~~ *The current implment with async and multithreading is not compatible with WSGI. Use Flask direcly please.*


---

## Scalability and Reliability:

Though the matching logic is naive, it has survived stress test of 10 concurrent connections within 1 seconds on a 2-core CPU server. We believe this is sufficient for most Touhou events' usage. 

---

## Configurable Settings:

> defs.py
1. `max_rounds`: max rounds for each game.
2. `max_hp`: initial HP
3. `place_guess_timeout`: timeout for guessing phase.
4. `agree_next_timeout`: timeout for reveal phase
5. `get_category_sampler`, `get_question_sampler`, `get_dmg_mult_selector`: determine how question is sampled and damage multipler is calculated for each round.

---

## Future Directions and How to Contribute

1. Enrich the question dataset. (scheduled)
    - Currently limited to official games and manga.
    - We welcome questions from well-known non-official manga, or real-world photos of locations related to the Touhou Project.

2. Add an "N-player" mode to support main-stage use at Touhou events. (not scheduled)
    - We welcome contributors with CS expertise to implement this functionality.

