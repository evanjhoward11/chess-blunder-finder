from flask import Flask, render_template, url_for, request, redirect, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap import Bootstrap
from flask_wtf.csrf import CSRFProtect
import os
from dotenv import load_dotenv
import requests
import json
import chess
from stockfish import Stockfish
import random

load_dotenv()
lichess_client_id = os.getenv("LICHESS_CLIENT_ID")
lichess_token = os.getenv("LICHESS_TOKEN")

LICHESS_ENDPOINT = "https://lichess.org"
THRESHOLD = 100
MATE_VALUE = 10**6
COUNTER_ID_RAND = 0

spaces = {
    1: " ",
    2: "  ",
    3: "   ",
    4: "    ",
    5: "     ",
    6: "      ",
    7: "       ",
    8: "        ",
}

FOLDER_PATH = "/static/img/"

images_dict = {
    "white": {
        "K": f"{FOLDER_PATH}white_sq_white_king.png",
        "k": f"{FOLDER_PATH}white_sq_black_king.png",
        "Q": f"{FOLDER_PATH}white_sq_white_queen.png",
        "q": f"{FOLDER_PATH}white_sq_black_queen.png",
        "R": f"{FOLDER_PATH}white_sq_white_rook.png",
        "r": f"{FOLDER_PATH}white_sq_black_rook.png",
        "B": f"{FOLDER_PATH}white_sq_white_bishop.png",
        "b": f"{FOLDER_PATH}white_sq_black_bishop.png",
        "N": f"{FOLDER_PATH}white_sq_white_knight.png",
        "n": f"{FOLDER_PATH}white_sq_black_knight.png",
        "P": f"{FOLDER_PATH}white_sq_white_pawn.png",
        "p": f"{FOLDER_PATH}white_sq_black_pawn.png",
        " ": f"{FOLDER_PATH}white_sq_none.png",
    },
    "black": {
        "K": f"{FOLDER_PATH}black_sq_white_king.png",
        "k": f"{FOLDER_PATH}black_sq_black_king.png",
        "Q": f"{FOLDER_PATH}black_sq_white_queen.png",
        "q": f"{FOLDER_PATH}black_sq_black_queen.png",
        "R": f"{FOLDER_PATH}black_sq_white_rook.png",
        "r": f"{FOLDER_PATH}black_sq_black_rook.png",
        "B": f"{FOLDER_PATH}black_sq_white_bishop.png",
        "b": f"{FOLDER_PATH}black_sq_black_bishop.png",
        "N": f"{FOLDER_PATH}black_sq_white_knight.png",
        "n": f"{FOLDER_PATH}black_sq_black_knight.png",
        "P": f"{FOLDER_PATH}black_sq_white_pawn.png",
        "p": f"{FOLDER_PATH}black_sq_black_pawn.png",
        " ": f"{FOLDER_PATH}black_sq_none.png",
    }
}


# Gets necessary db id and db row, then extracts/builds data from row
def html_data(id_rand_list):
    db_id = id_rand_list[COUNTER_ID_RAND]
    fen_row = db.session.get(Fen, db_id)

    color = fen_row.color.title()
    files_array = fen_to_board(fen_row.fen, color)
    game_url = f"{LICHESS_ENDPOINT}/{fen_row.game_id}/{fen_row.color}#{fen_row.ply}"
    solution = fen_row.solution_san
    return db_id, files_array, game_url, color, solution


# Converts a FEN to 8x8 array of img file locations
def fen_to_board(fen, player_color):
    separated_chars = []
    sq_color = "white"
    counter_sq = 1
    files_array = []

    fen_rows = fen.split()[0].split("/")

    # Convert each string into a parsed out list
    for row in fen_rows:
        separated_chars.append(list(row))

    # If a char is a number, replace it with an equivalent number of spaces in place
    for row in separated_chars:
        for i, c in enumerate(row):
            if c.isnumeric():
                row[i] = spaces[int(c)]

    # Join and then expand strings
    fen_consolidated = ["".join(row) for row in separated_chars]
    fen_expanded = [list(row) for row in fen_consolidated]

    # Append correct piece/square file name into 8x8 matrix
    for row in fen_expanded:
        cols = []
        for char in row:
            cols.append(images_dict[sq_color][char])
            if counter_sq % 8 != 0:
                if sq_color == "white":
                    sq_color = "black"
                else:
                    sq_color = "white"
            counter_sq += 1
        files_array.append(cols)
    
    # If color is black, flip the board orientation
    if player_color == "Black":
        files_array = [i[::-1] for i in files_array[::-1]]
    
    return files_array


# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.getenv('SQLALCHEMY_DATABASE_URI')}\\Chess Blunders Finder\\instance\\puzzles.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
Bootstrap(app)


# Configure the database
class Fen(db.Model):
    __tablename__ = "positions"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, nullable=False)
    game_id = db.Column(db.String, nullable=False)
    fen = db.Column(db.String, nullable=False)
    ply = db.Column(db.Integer, nullable=False)
    color = db.Column(db.String, nullable=False)
    solution_san = db.Column(db.String, nullable=False)

with app.app_context():
    db.create_all()


# Configure and initialize Stockfish engine
stockfish_path = "Stockfish 15\\stockfish-windows-2022-x86-64-avx2.exe"
engine_depth = 17
stockfish_parameters = {
    "Threads": 2,
    "Hash": 2**11,
}
stockfish = Stockfish(path=stockfish_path, depth=engine_depth, parameters=stockfish_parameters)


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        lichess_username = request.form.get("username")
        num_games = request.form.get("num_games")
        time_formats = request.form.getlist("time_format")
        game_mode = request.form.get("game_mode")

        if not time_formats:
            time_formats = ['rapid']

        lichess_parameters = {
            "max": num_games,
            "perfType": time_formats,
            "rated": game_mode,
        }
        header = {
            "Accept": "application/x-ndjson"
        }

        # Use Lichess API to get user's games
        try:
            response = requests.get(url=f"{LICHESS_ENDPOINT}/api/games/user/{lichess_username}", params=lichess_parameters, headers=header)
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            flash("Couldn't connect to Lichess. Check your username and internet connection.")
            return redirect(url_for("home"))

        # Convert string of multiple jsons (games) to proper json format (add commas between games, outer brackets to turn it into a list, etc)
        data_raw = response.text
        data_raw = data_raw.replace('\n', '')
        data_raw = data_raw.replace('}{', '},{')
        data_raw = "[" + data_raw + "]"
        games = json.loads(data_raw)

        for game in games:
            ply = 0
            # Extract game id and determine color
            game_id = game["id"]
            if game["players"]["white"]["user"]["name"] == lichess_username:
                user_color_bool = True
                user_color = "white"
            else:
                user_color_bool = False
                user_color = "black"

            # Check if the game id with this specific user (not their opponent) already exists in the db; if not, then analyze the game
            # Note: this specific check is important cause it'll allow opponent to also analyze the game from their perspective
            query_username_game_id = Fen.query.filter(Fen.username==lichess_username, Fen.game_id==game_id).first()

            if query_username_game_id is None:
                oppo_blunder_flag = False
                # Initialize chess board and get evaluation of starting position
                board = chess.Board()
                stockfish.set_fen_position("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
                moves = game["moves"].split()
                pos_eval1 = stockfish.get_evaluation()["value"]

                for move in moves:
                    uci_move = board.push_san(move)
                    stockfish.make_moves_from_current_position([uci_move])
                    ply += 1

                    pos_eval2_raw = stockfish.get_evaluation()  # {'type': 'cp', 'value': 35}

                    # If there is a mate rather than a cp value, convert the cp value to some large number (ex. 10^6)
                    if pos_eval2_raw["type"] == "mate":
                        pos_eval2_raw["value"] = MATE_VALUE * abs(pos_eval2_raw["value"])/pos_eval2_raw["value"]
                    pos_eval2 = pos_eval2_raw["value"]

                    if abs(pos_eval2 - pos_eval1) >= THRESHOLD:
                        # 1) if user's opponent blunders, then set a flag and save puzzle data
                        if board.turn == user_color_bool:
                            oppo_blunder_flag = True
                            fen = stockfish.get_fen_position()
                            best_move_uci = stockfish.get_best_move()
                            best_move_obj = chess.Move.from_uci(best_move_uci)
                            best_move_san = board.san(best_move_obj)
                        # 2) if user blunders right after their opponent blunders, save puzzle data to db
                        elif oppo_blunder_flag:
                            oppo_blunder_flag = False
                            new_fen = Fen(
                                username = lichess_username,
                                game_id = game_id,
                                fen = fen,
                                ply = ply-1,
                                color = user_color,
                                solution_san = best_move_san
                            )
                            db.session.add(new_fen)
                            db.session.commit()

                    else:
                        oppo_blunder_flag = False

                    pos_eval1 = pos_eval2
        
        # Query all the Fens/ids of a specific user, then generate randomly ordered list of all the db ids
        rows_of_username = Fen.query.filter_by(username=lichess_username).all()
        ids = [row.id for row in rows_of_username]
        id_rand_list = random.sample(ids, len(ids))

        if not id_rand_list:
            flash("No blunders were found. Try changing your search settings.")
            return render_template("index.html")

        session["id_list"] = id_rand_list
        return redirect(url_for("puzzles", lichess_username=lichess_username))
 
    return render_template("index.html")


@app.route("/<lichess_username>", methods=["GET", "POST"])
def puzzles(lichess_username):
    global COUNTER_ID_RAND
    solution = ""

    id_rand_list = session["id_list"]
    db_id, files_array, game_url, color, solution = html_data(id_rand_list)

    if request.method == "GET":
        return render_template("puzzles.html", db_id=db_id, lichess_username=lichess_username, color=color, game_url=game_url, files_array=files_array)

    elif request.form.get("next_puzzle_button"):
        COUNTER_ID_RAND += 1
        if COUNTER_ID_RAND >= len(id_rand_list):
            COUNTER_ID_RAND = 0
        db_id, files_array, game_url, color, solution = html_data(id_rand_list)
        return render_template("puzzles.html", db_id=db_id, lichess_username=lichess_username, color=color, game_url=game_url, files_array=files_array)

    elif request.form.get("solution_button"):
        return render_template("puzzles.html", db_id=db_id, lichess_username=lichess_username, color=color, game_url=game_url, files_array=files_array, solution=solution)


@app.route("/<lichess_username>/<int:db_id>", methods=["GET", "POST"])
def delete(lichess_username, db_id):
    # Remove db id from list of random ids
    id_rand_list = session["id_list"]
    id_rand_list.remove(db_id)
    session["id_list"] = id_rand_list
    # Remove fen from db
    fen_to_delete = db.session.get(Fen, db_id)
    db.session.delete(fen_to_delete)
    db.session.commit()

    if id_rand_list:
        return redirect(url_for('puzzles', lichess_username=lichess_username))
    else:
        flash("All puzzles were deleted. Analyze more games to get more puzzles.")
        return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=False)
