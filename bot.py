import discord
import random
import os
import webserver
import json
import mysql.connector
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
from dotenv import load_dotenv
from functools import partial

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")

# Configuración del bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Emojis para fichas
FICHAS = {"X": "❎", "O": "🅾️", " ": "⬜"}

# Conectar a la base de datos
db = mysql.connector.connect(
    host=MYSQL_HOST,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    database=MYSQL_DATABASE
)
cursor = db.cursor()

# Crear tablas si no existen
cursor.execute("""
CREATE TABLE IF NOT EXISTS partidas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guild_id BIGINT,
    message_id BIGINT,
    tablero VARCHAR(9),
    jugador_actual CHAR(1),
    modo_vs_bot BOOLEAN,
    partida_activa BOOLEAN,
    jugadores JSON,
    dificultad VARCHAR(10)
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS stats (
    guild_id BIGINT,
    user VARCHAR(255),
    wins INT DEFAULT 0,
    losses INT DEFAULT 0,
    draws INT DEFAULT 0,
    PRIMARY KEY (guild_id, user)
)
""")
db.commit()

# Almacenar partidas activas (clave: ID del mensaje)
partidas = {}

# Almacenar estadísticas de jugadores por servidor
stats = {}

def save_partidas():
    cursor.execute("DELETE FROM partidas")
    for message_id, game in partidas.items():
        cursor.execute("""
        INSERT INTO partidas (guild_id, message_id, tablero, jugador_actual, modo_vs_bot, partida_activa, jugadores, dificultad)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (game.guild_id, message_id, ''.join(game.tablero), game.jugador_actual, game.modo_vs_bot, game.partida_activa, json.dumps(game.jugadores), game.dificultad))
    db.commit()

def load_partidas():
    global partidas
    cursor.execute("SELECT * FROM partidas")
    for row in cursor.fetchall():
        game = TicTacToeGame(guild_id=row[1], dificultad=row[8])
        game.tablero = list(row[3])
        game.jugador_actual = row[4]
        game.modo_vs_bot = row[5]
        game.partida_activa = row[6]
        game.jugadores = json.loads(row[7])
        partidas[row[2]] = game

def save_stats():
    cursor.execute("DELETE FROM stats")
    for guild_id, users in stats.items():
        for user, user_stats in users.items():
            cursor.execute("""
            INSERT INTO stats (guild_id, user, wins, losses, draws)
            VALUES (%s, %s, %s, %s, %s)
            """, (guild_id, user, user_stats["wins"], user_stats["losses"], user_stats["draws"]))
    db.commit()

def load_stats():
    global stats
    cursor.execute("SELECT * FROM stats")
    for row in cursor.fetchall():
        guild_id, user, wins, losses, draws = row
        if guild_id not in stats:
            stats[guild_id] = {}
        stats[guild_id][user] = {"wins": wins, "losses": losses, "draws": draws}

def update_stats(guild_id, winner, loser):
    """Actualiza las estadísticas tras una victoria."""
    cursor.execute("""
        INSERT INTO stats (guild_id, user, wins, losses, draws)
        VALUES (%s, %s, 1, 0, 0)
        ON DUPLICATE KEY UPDATE wins = wins + 1
    """, (guild_id, winner))
    cursor.execute("""
        INSERT INTO stats (guild_id, user, wins, losses, draws)
        VALUES (%s, %s, 0, 1, 0)
        ON DUPLICATE KEY UPDATE losses = losses + 1
    """, (guild_id, loser))
    db.commit()

def update_draw(guild_id, player1, player2):
    """Actualiza las estadísticas en caso de empate."""
    cursor.execute("""
        INSERT INTO stats (guild_id, user, wins, losses, draws)
        VALUES (%s, %s, 0, 0, 1)
        ON DUPLICATE KEY UPDATE draws = draws + 1
    """, (guild_id, player1))
    cursor.execute("""
        INSERT INTO stats (guild_id, user, wins, losses, draws)
        VALUES (%s, %s, 0, 0, 1)
        ON DUPLICATE KEY UPDATE draws = draws + 1
    """, (guild_id, player2))
    db.commit()

class TicTacToeGame:
    def __init__(self, guild_id, dificultad="dificil"):
        self.guild_id = guild_id
        self.tablero = [" "] * 9
        self.jugador_actual = "X"
        self.modo_vs_bot = False
        self.partida_activa = False
        self.jugadores = {}
        self.dificultad = dificultad  # "facil", "medio", "dificil"

    def verificar_ganador(self):
        combinaciones_ganadoras = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],
            [0, 3, 6], [1, 4, 7], [2, 5, 8],
            [0, 4, 8], [2, 4, 6]
        ]
        for a, b, c in combinaciones_ganadoras:
            if self.tablero[a] == self.tablero[b] == self.tablero[c] and self.tablero[a] != " ":
                return True
        return False

class TicTacToeView(View):
    def __init__(self, game, message_id):
        super().__init__(timeout=300)
        self.game = game
        self.message_id = message_id
        # Crear 9 botones para las casillas
        for i in range(9):
            button = Button(style=discord.ButtonStyle.secondary, label=FICHAS[self.game.tablero[i]], row=i // 3)
            button.callback = partial(self.handle_click, index=i)
            self.add_item(button)
    
    async def disable_buttons(self, interaction: discord.Interaction):
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

    async def check_endgame(self, interaction: discord.Interaction):
        if self.game.verificar_ganador():
            self.game.partida_activa = False
            await self.disable_buttons(interaction)
            ganador_marker = self.game.jugador_actual
            ganador = self.game.jugadores[ganador_marker]
            perdedor_marker = "X" if ganador_marker == "O" else "O"
            perdedor = self.game.jugadores[perdedor_marker]
            update_stats(interaction.guild.id, ganador, perdedor)
            await interaction.message.reply(f"🏆 ¡{ganador} ha ganado con {FICHAS[ganador_marker]}!\n📊 Estadísticas actualizadas.")
            if not interaction.response.is_done():
                await interaction.response.defer()
            if self.message_id in partidas:
                del partidas[self.message_id]
                save_partidas()
            return True
        elif " " not in self.game.tablero:
            self.game.partida_activa = False
            await self.disable_buttons(interaction)
            update_draw(interaction.guild.id, self.game.jugadores["X"], self.game.jugadores["O"])
            await interaction.message.reply("😲 ¡Empate!\n📊 Estadísticas actualizadas.")
            if not interaction.response.is_done():
                await interaction.response.defer()
            if self.message_id in partidas:
                del partidas[self.message_id]
                save_partidas()
            return True
        return False

    def evaluate(self, board):
        wins = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6)
        ]
        for a, b, c in wins:
            if board[a] == board[b] == board[c] and board[a] != " ":
                return 10 if board[a] == "O" else -10
        return 0

    def minimax(self, board, depth, is_maximizing):
        score = self.evaluate(board)
        if score == 10 or score == -10:
            return score
        if " " not in board:
            return 0

        if is_maximizing:
            best = -1000
            for i in range(9):
                if board[i] == " ":
                    board[i] = "O"
                    best = max(best, self.minimax(board, depth + 1, False))
                    board[i] = " "
            return best
        else:
            best = 1000
            for i in range(9):
                if board[i] == " ":
                    board[i] = "X"
                    best = min(best, self.minimax(board, depth + 1, True))
                    board[i] = " "
            return best

    async def bot_move(self, interaction: discord.Interaction):
        board = self.game.tablero[:]
        best_move = None
        dificultad = self.game.dificultad.lower()
        if dificultad == "facil":
            # 70% de probabilidades de hacer un movimiento aleatorio
            if random.random() < 0.7:
                available_moves = [i for i in range(9) if board[i] == " "]
                best_move = random.choice(available_moves)
            else:
                best_score = -1000
                for i in range(9):
                    if board[i] == " ":
                        board[i] = "O"
                        score = self.minimax(board, 0, False)
                        board[i] = " "
                        if score > best_score:
                            best_score = score
                            best_move = i
        elif dificultad == "medio":
            # 50% de probabilidades de hacer un movimiento aleatorio
            if random.random() < 0.5:
                available_moves = [i for i in range(9) if board[i] == " "]
                best_move = random.choice(available_moves)
            else:
                best_score = -1000
                for i in range(9):
                    if board[i] == " ":
                        board[i] = "O"
                        score = self.minimax(board, 0, False)
                        board[i] = " "
                        if score > best_score:
                            best_score = score
                            best_move = i
        else:  # "dificil" o cualquier otro valor
            best_score = -1000
            for i in range(9):
                if board[i] == " ":
                    board[i] = "O"
                    score = self.minimax(board, 0, False)
                    board[i] = " "
                    if score > best_score:
                        best_score = score
                        best_move = i

        if best_move is not None:
            self.game.tablero[best_move] = "O"
            self.children[best_move].label = FICHAS["O"]
            self.children[best_move].disabled = True
            if await self.check_endgame(interaction):
                return
        self.game.jugador_actual = "X"
        await interaction.message.edit(view=self)

    async def handle_click(self, interaction: discord.Interaction, index: int):
        if not self.game.partida_activa:
            await interaction.response.send_message("⚠️ No hay una partida en curso. Usa `/iniciar` para jugar.", ephemeral=True)
            return

        current_player = self.game.jugadores[self.game.jugador_actual]
        if interaction.user.mention != current_player:
            await interaction.response.send_message("⚠️ No es tu turno.", ephemeral=True)
            return

        if self.game.tablero[index] != " ":
            await interaction.response.send_message("❌ Esa casilla ya está ocupada.", ephemeral=True)
            return

        self.game.tablero[index] = self.game.jugador_actual
        self.children[index].label = FICHAS[self.game.jugador_actual]
        self.children[index].disabled = True

        if await self.check_endgame(interaction):
            return

        self.game.jugador_actual = "O" if self.game.jugador_actual == "X" else "X"
        await interaction.response.edit_message(view=self)

        if self.game.modo_vs_bot and self.game.jugador_actual == "O":
            await self.bot_move(interaction)

@bot.tree.command(name="iniciar", description="Utiliza solo /iniciar para jugar una partida contra el bot.")
@app_commands.describe(oponente="Selecciona un oponente en este servidor para iniciar una partida.")
@app_commands.describe(dificultad='Selecciona la dificultad para jugar contra el bot. Por defecto: "Medio".')

@app_commands.choices(dificultad=[
    app_commands.Choice(name="Fácil", value="facil"),
    app_commands.Choice(name="Medio", value="medio"),
    app_commands.Choice(name="Difícil", value="dificil")
])
async def iniciar(interaction: discord.Interaction, oponente: discord.Member = None, dificultad: app_commands.Choice[str] = None):
    if oponente is not None and oponente.id != bot.user.id and dificultad is not None:
        await interaction.response.send_message("⚠️ El nivel de dificultad solo se puede ajustar al jugar contra el bot. Iniciando partida contra jugador.", ephemeral=True)
        dificultad = None

    if oponente is None or oponente.id == bot.user.id:
        # Jugar contra el bot: se utiliza la dificultad especificada (por defecto "medio")
        dificultad = dificultad.value if dificultad else "medio"
        game = TicTacToeGame(interaction.guild.id, dificultad=dificultad)
        game.modo_vs_bot = True
        game.jugadores = {"X": interaction.user.mention, "O": bot.user.mention}
    else:
        # Jugar contra otro jugador; se ignora la dificultad
        game = TicTacToeGame(interaction.guild.id)
        game.jugadores = {"X": interaction.user.mention, "O": oponente.mention}

    game.partida_activa = True
    view = TicTacToeView(game, interaction.id)
    embed = discord.Embed(
        title="🎲 ¡Tres en raya!",
        description=f"{game.jugadores['X']} contra {game.jugadores['O']}\n\n🎮 ¡QUE COMIENCE EL JUEGO! 🎮\n\n🔄 Turno de {game.jugadores[game.jugador_actual]} con {FICHAS['X']} !",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, view=view)
    partidas[interaction.id] = game
    save_partidas()

@bot.tree.command(name="reiniciar", description="Reinicia la partida actual")
async def reiniciar(interaction: discord.Interaction):
    if interaction.id in partidas:
        del partidas[interaction.id]
        save_partidas()
        await interaction.response.send_message("🔄 La partida ha sido reiniciada. Usa `/iniciar` para jugar de nuevo.")
    else:
        await interaction.response.send_message("⚠️ No hay ninguna partida activa para reiniciar.")

@bot.tree.command(name="stats", description="Muestra las estadísticas de tus partidas")
async def stats_command(interaction: discord.Interaction):
    await interaction.response.defer()  # Defer the response to give more time
    guild_id = interaction.guild.id
    user = interaction.user.mention

    # Consultar la base de datos para obtener las estadísticas del usuario
    cursor.execute("SELECT wins, losses, draws FROM stats WHERE guild_id = %s AND user = %s", (guild_id, user))
    result = cursor.fetchone()
    if result:
        wins, losses, draws = result
    else:
        wins, losses, draws = 0, 0, 0

    embed = discord.Embed(
        title="📊 Tus estadísticas",
        description=f"Victorias: {wins}\nDerrotas: {losses}\nEmpates: {draws}",
        color=discord.Color.green()
    )
    await interaction.followup.send(embed=embed)  # Send the actual message without ephemeral

@bot.event
async def on_ready():
    load_partidas()
    load_stats()
    await bot.tree.sync()
    print(f"Bot conectado como {bot.user}")

webserver.keep_alive()
bot.run(TOKEN)