import discord
import random
import os
import webserver
import json
import mysql.connector
import asyncio  # Asegúrate de importar asyncio al inicio del archivo
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
from dotenv import load_dotenv
from functools import partial

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
MYSQL_HOST = os.getenv("MYSQLHOST")
MYSQL_USER = os.getenv("MYSQLUSER")
MYSQL_PASSWORD = os.getenv("MYSQLPASSWORD")
MYSQL_DATABASE = os.getenv("MYSQLDATABASE")

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
        """, (
            game.guild_id, message_id, ''.join(game.tablero),
            game.jugador_actual, game.modo_vs_bot, game.partida_activa,
            json.dumps(game.jugadores), game.dificultad
        ))
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
            """, (
                guild_id, user, user_stats["wins"],
                user_stats["losses"], user_stats["draws"]
            ))
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
        self.jugador_actual = "X"  # Se sobreescribirá según la selección
        self.modo_vs_bot = False
        self.partida_activa = False
        self.jugadores = {}
        self.dificultad = dificultad  # "facil", "medio", "dificil"
        self.bot_marker = None  # Se asigna al iniciar partida vs bot

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
        self.message = None  # Almacena el mensaje asociado a la vista
        # Crear 9 botones para las casillas
        for i in range(9):
            button = Button(
                style=self.get_button_style(self.game.tablero[i]),
                label=FICHAS[self.game.tablero[i]],
                row=i // 3
            )
            button.callback = partial(self.handle_click, index=i)
            self.add_item(button)

    def get_button_style(self, symbol):
        if symbol == "X":
            return discord.ButtonStyle.success
        elif symbol == "O":
            return discord.ButtonStyle.danger
        else:
            return discord.ButtonStyle.secondary

    async def disable_buttons(self, interaction: discord.Interaction):
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

    async def send_game_end(self, interaction: discord.Interaction):
        """Envía el mensaje final común para victoria o empate."""
        embed_end = discord.Embed(
            title="Juego terminado",
            description="Selecciona una opción:",
            color=discord.Color.purple()
        )
        await interaction.channel.send(embed=embed_end, view=GameEndView(self.game, interaction.channel))
        if self.message_id in partidas:
            del partidas[self.message_id]
            save_partidas()

    async def check_endgame(self, interaction: discord.Interaction):
        if self.game.verificar_ganador():
            self.game.partida_activa = False
            await self.disable_buttons(interaction)
            ganador_marker = self.game.jugador_actual
            ganador = self.game.jugadores[ganador_marker]
            perdedor_marker = "X" if ganador_marker == "O" else "O"
            perdedor = self.game.jugadores[perdedor_marker]
            update_stats(interaction.guild.id, ganador, perdedor)
            await interaction.message.reply(
                f"🏆 ¡{ganador} ha ganado con {FICHAS[ganador_marker]}!\n📊 Estadísticas actualizadas."
            )
            await self.send_game_end(interaction)
            if not interaction.response.is_done():
                await interaction.response.defer()
            return True
        elif " " not in self.game.tablero:
            self.game.partida_activa = False
            await self.disable_buttons(interaction)
            update_draw(interaction.guild.id, self.game.jugadores["X"], self.game.jugadores["O"])
            await interaction.message.reply("😲 ¡Empate!\n📊 Estadísticas actualizadas.")
            await self.send_game_end(interaction)
            if not interaction.response.is_done():
                await interaction.response.defer()
            return True
        return False

    def evaluate(self, board):
        if self.game.modo_vs_bot and self.game.bot_marker:
            bot_marker = self.game.bot_marker
            human_marker = "X" if bot_marker == "O" else "O"
        else:
            bot_marker = "O"
            human_marker = "X"
        wins = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6)
        ]
        for a, b, c in wins:
            if board[a] == board[b] == board[c] and board[a] != " ":
                if board[a] == bot_marker:
                    return 10
                elif board[a] == human_marker:
                    return -10
        return 0

    def minimax(self, board, depth, is_maximizing, max_depth=3):
        if depth >= max_depth:
            return 0  # Detener la recursión en la profundidad máxima
        if self.game.modo_vs_bot and self.game.bot_marker:
            bot_marker = self.game.bot_marker
            human_marker = "X" if bot_marker == "O" else "O"
        else:
            bot_marker = "O"
            human_marker = "X"
        score = self.evaluate(board)
        if score == 10 or score == -10:
            return score
        if " " not in board:
            return 0

        if is_maximizing:
            best = -1000
            for i in range(9):
                if board[i] == " ":
                    board[i] = bot_marker
                    best = max(best, self.minimax(board, depth + 1, False))
                    board[i] = " "
            return best
        else:
            best = 1000
            for i in range(9):
                if board[i] == " ":
                    board[i] = human_marker
                    best = min(best, self.minimax(board, depth + 1, True))
                    board[i] = " "
            return best

    async def bot_move(self, interaction: discord.Interaction, first_turn=False):
        if self.game.modo_vs_bot and self.game.bot_marker:
            bot_marker = self.game.bot_marker
            human_marker = "X" if bot_marker == "O" else "O"
        else:
            bot_marker = "O"
            human_marker = "X"
        board = self.game.tablero[:]
        best_move = None
        dificultad = self.game.dificultad.lower()
        if dificultad == "facil":
            if random.random() < 0.7:
                available_moves = [i for i in range(9) if board[i] == " "]
                best_move = random.choice(available_moves)
            else:
                best_score = -1000
                for i in range(9):
                    if board[i] == " ":
                        board[i] = bot_marker
                        score = self.minimax(board, 0, False)
                        board[i] = " "
                        if score > best_score:
                            best_score = score
                            best_move = i
        elif dificultad == "medio":
            if random.random() < 0.5:
                available_moves = [i for i in range(9) if board[i] == " "]
                best_move = random.choice(available_moves)
            else:
                best_score = -1000
                for i in range(9):
                    if board[i] == " ":
                        board[i] = bot_marker
                        score = self.minimax(board, 0, False)
                        board[i] = " "
                        if score > best_score:
                            best_score = score
                            best_move = i
        else:
            best_score = -1000
            for i in range(9):
                if board[i] == " ":
                    board[i] = bot_marker
                    score = self.minimax(board, 0, False)
                    board[i] = " "
                    if score > best_score:
                        best_score = score
                        best_move = i

        if board == [" "] * 9:
            best_move = 4 if board[4] == " " else random.choice([0, 2, 6, 8])
        else:
            pass

        embed = discord.Embed(
            title="🎲 ¡Tres en raya!",
            description=(
                f"{self.game.jugadores['X']} vs {self.game.jugadores['O']}\n\n"
                f"🔄 Turno de {self.game.jugadores[bot_marker]} con {FICHAS[bot_marker]}!"
            ),
            color=discord.Color.blue()
        )
        await self.message.edit(embed=embed, view=self)

        if not first_turn:
            await asyncio.sleep(0.3)

        if best_move is not None:
            self.game.tablero[best_move] = bot_marker
            self.children[best_move].label = FICHAS[bot_marker]
            self.children[best_move].style = self.get_button_style(bot_marker)
            self.children[best_move].disabled = True
            if await self.check_endgame(interaction):
                return
        self.game.jugador_actual = human_marker

        embed = discord.Embed(
            title="🎲 ¡Tres en raya!",
            description=(
                f"{self.game.jugadores['X']} vs {self.game.jugadores['O']}\n\n"
                f"🔄 Turno de {self.game.jugadores[self.game.jugador_actual]} con {FICHAS[self.game.jugador_actual]}!"
            ),
            color=discord.Color.blue()
        )
        await self.message.edit(embed=embed, view=self)

    async def handle_click(self, interaction: discord.Interaction, index: int):
        if not self.game.partida_activa:
            await interaction.response.send_message(
                "⚠️ No hay una partida en curso. Usa `/start` para jugar.",
                ephemeral=True
            )
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
        self.children[index].style = self.get_button_style(self.game.jugador_actual)
        self.children[index].disabled = True

        if await self.check_endgame(interaction):
            return

        if self.game.modo_vs_bot:
            self.game.jugador_actual = self.game.bot_marker
            await interaction.response.edit_message(view=self)
            await self.bot_move(interaction)
        else:
            self.game.jugador_actual = "O" if self.game.jugador_actual == "X" else "X"
            embed = discord.Embed(
                title="🎲 ¡Tres en raya!",
                description=(
                    f"{self.game.jugadores['X']} vs {self.game.jugadores['O']}\n\n"
                    f"🔄 Turno de {self.game.jugadores[self.game.jugador_actual]} con {FICHAS[self.game.jugador_actual]}!"
                ),
                color=discord.Color.blue()
            )
            await interaction.response.edit_message(embed=embed, view=self)

class GameEndView(discord.ui.View):
    def __init__(self, game, original_channel):
        super().__init__(timeout=180)
        self.game = game
        self.original_channel = original_channel

    def es_jugador_actual(self, user):
        return user.mention in self.game.jugadores.values()

    @discord.ui.button(label="Reiniciar", style=discord.ButtonStyle.success)
    async def reiniciar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.es_jugador_actual(interaction.user):
            await interaction.response.send_message("❌ Solo los jugadores de esta partida pueden usar este botón.", ephemeral=True)
            return

        guild_id = self.game.guild_id
        dificultad = self.game.dificultad
        jugadores = self.game.jugadores

        await interaction.response.defer()

        if bot.user.mention in jugadores.values():
            user_ficha = "O" if jugadores["X"] == bot.user.mention else "X"
            await reiniciar_partida(interaction, None, dificultad, user_ficha, jugadores=jugadores)
        else:
            user_ficha = "X" if interaction.user.mention == jugadores["X"] else "O"
            oponente = interaction.guild.get_member(int(jugadores["X"].strip("<@!>"))) if user_ficha == "O" else interaction.guild.get_member(int(jugadores["O"].strip("<@!>")))
            await reiniciar_partida(interaction, oponente, None, user_ficha, jugadores=jugadores)

        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="Terminar", style=discord.ButtonStyle.danger)
    async def terminar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.es_jugador_actual(interaction.user):
            await interaction.response.send_message("❌ Solo los jugadores de esta partida pueden usar este botón.", ephemeral=True)
            return

        await interaction.response.defer()

        for child in self.children:
            child.disabled = True

        embed = discord.Embed(
            title="Juego terminado",
            description="La partida se ha terminado.",
            color=discord.Color.purple()
        )
        await interaction.message.edit(embed=embed, view=self)
        self.stop()

# Función auxiliar para reiniciar la partida usando la configuración anterior
async def reiniciar_partida(interaction: discord.Interaction, oponente: discord.Member, dificultad: str, user_ficha: str, *, jugadores=None):
    game = TicTacToeGame(interaction.guild.id, dificultad=dificultad if dificultad else "medio")
    game.partida_activa = True
    if jugadores:
        game.jugadores = jugadores
        if bot.user.mention in jugadores.values():
            game.modo_vs_bot = True
            game.bot_marker = "X" if jugadores["X"] == bot.user.mention else "O"
    else:
        if oponente and oponente.id != bot.user.id:
            if user_ficha == "X":
                game.jugadores = {"X": interaction.user.mention, "O": oponente.mention}
            else:
                game.jugadores = {"X": oponente.mention, "O": interaction.user.mention}
        else:
            game.modo_vs_bot = True
            if user_ficha == "X":
                game.jugadores = {"X": interaction.user.mention, "O": bot.user.mention}
                game.bot_marker = "O"
            else:
                game.jugadores = {"X": bot.user.mention, "O": interaction.user.mention}
                game.bot_marker = "X"
    game.jugador_actual = "X"

    view = TicTacToeView(game, interaction.id)
    embed = discord.Embed(
        title="🎲 ¡Tres en raya!",
        description=(
            f"{game.jugadores['X']} vs {game.jugadores['O']}\n\n"
            "🎮 ¡QUE COMIENCE EL JUEGO! 🎮\n\n"
            f"🔄 Turno de {game.jugadores[game.jugador_actual]} con {FICHAS[game.jugador_actual]}!"
        ),
        color=discord.Color.blue()
    )
    message = await interaction.channel.send(embed=embed, view=view)
    partidas[interaction.id] = game
    save_partidas()
    view.message = message
    if game.modo_vs_bot and ((user_ficha == "O") or (user_ficha == "X" and game.bot_marker == "X")):
        await view.bot_move(interaction, first_turn=True)

# Vista para la selección de ficha
class TokenSelectionView(discord.ui.View):
    def __init__(self, original_interaction: discord.Interaction, oponente: discord.Member, dificultad: str):
        super().__init__(timeout=60)
        self.original_interaction = original_interaction
        self.oponente = oponente
        self.dificultad = dificultad

    @discord.ui.button(label="❎", style=discord.ButtonStyle.success)
    async def select_x(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_interaction.user.id:
            await interaction.response.send_message("No puedes seleccionar esta opción.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        for child in self.children:
            child.disabled = True
            if child != button:
                child.style = discord.ButtonStyle.secondary
        try:
            await interaction.edit_original_response(view=self)
        except Exception as e:
            print("Error al editar el mensaje:", e)
        await iniciar_partida(self.original_interaction, self.oponente, self.dificultad, "X")
        self.stop()

    @discord.ui.button(label="🅾️", style=discord.ButtonStyle.danger)
    async def select_o(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_interaction.user.id:
            await interaction.response.send_message("No puedes seleccionar esta opción.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        for child in self.children:
            child.disabled = True
            if child != button:
                child.style = discord.ButtonStyle.secondary
        try:
            await interaction.edit_original_response(view=self)
        except Exception as e:
            print("Error al editar el mensaje:", e)
        await iniciar_partida(self.original_interaction, self.oponente, self.dificultad, "O", bot_first=True)
        self.stop()

# Función para iniciar la partida según la ficha seleccionada
async def iniciar_partida(interaction: discord.Interaction, oponente: discord.Member, dificultad: str, user_ficha: str, bot_first: bool = False):
    if oponente is not None and oponente.id != bot.user.id:
        game = TicTacToeGame(interaction.guild.id)
        if user_ficha == "X":
            game.jugadores = {"X": interaction.user.mention, "O": oponente.mention}
        else:
            game.jugadores = {"X": oponente.mention, "O": interaction.user.mention}
    else:
        dificultad = dificultad if dificultad else "medio"
        game = TicTacToeGame(interaction.guild.id, dificultad=dificultad)
        game.modo_vs_bot = True
        if user_ficha == "X":
            game.jugadores = {"X": interaction.user.mention, "O": bot.user.mention}
            game.bot_marker = "O"
        else:
            game.jugadores = {"X": bot.user.mention, "O": interaction.user.mention}
            game.bot_marker = "X"

    game.jugador_actual = "X"
    game.partida_activa = True

    view = TicTacToeView(game, interaction.id)
    embed = discord.Embed(
        title="🎲 ¡Tres en raya!",
        description=(
            f"{game.jugadores['X']} vs {game.jugadores['O']}\n\n"
            "🎮 ¡QUE COMIENCE EL JUEGO! 🎮\n\n"
            f"🔄 Turno de {game.jugadores[game.jugador_actual]} con {FICHAS[game.jugador_actual]}!"
        ),
        color=discord.Color.blue()
    )
    message = await interaction.followup.send(embed=embed, view=view)
    partidas[interaction.id] = game
    save_partidas()
    view.message = message
    if bot_first and game.modo_vs_bot:
        await view.bot_move(interaction, first_turn=True)

@bot.tree.command(name="start", description="Inicia una partida de Tres en Raya.")
@app_commands.describe(
    oponente="Menciona un oponente para jugar contra él, o déjalo vacío para jugar contra el bot.",
    dificultad="Selecciona la dificultad (solo disponible contra el bot)."
)
@app_commands.choices(
    dificultad=[
        app_commands.Choice(name="Fácil", value="facil"),
        app_commands.Choice(name="Medio", value="medio"),
        app_commands.Choice(name="Difícil", value="dificil")
    ]
)
async def start(
    interaction: discord.Interaction, 
    oponente: discord.Member = None, 
    dificultad: app_commands.Choice[str] = None
):
    if oponente is not None and oponente.id != bot.user.id:
        if dificultad is not None:
            await interaction.response.send_message(
                "⚠️ No puedes establecer dificultad cuando juegas contra otro usuario.",
                ephemeral=True
            )
            return
        dificultad_value = None
    else:
        dificultad_value = dificultad.value if dificultad else "medio"
    view = TokenSelectionView(interaction, oponente, dificultad_value)
    embed = discord.Embed(
        title="🎲 ¡Tres en raya!",
        description="Selecciona tu ficha:",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="stats", description="Muestra las estadísticas de tus partidas o las de otro usuario")
@app_commands.describe(usuario="Menciona a un usuario para ver sus estadísticas")
async def stats_command(interaction: discord.Interaction, usuario: discord.Member = None):
    await interaction.response.defer()
    guild_id = interaction.guild.id
    user = usuario.mention if usuario else interaction.user.mention
    user_display_name = usuario.display_name if usuario else interaction.user.display_name
    cursor.execute("SELECT wins, losses, draws FROM stats WHERE guild_id = %s AND user = %s", (guild_id, user))
    result = cursor.fetchone()
    if result:
        wins, losses, draws = result
    else:
        wins, losses, draws = 0, 0, 0
    embed = discord.Embed(
        title=f"📊 Estadísticas de {user_display_name}",
        description=f"Victorias: {wins}\nDerrotas: {losses}\nEmpates: {draws}",
        color=discord.Color.green()
    )
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="leaderboard", description="Muestra el top de jugadores con más victorias.")
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    guild_id = interaction.guild.id
    cursor.execute("""
        SELECT user, wins, losses FROM stats
        WHERE guild_id = %s
        ORDER BY wins DESC, losses ASC
        LIMIT 100
    """, (guild_id,))
    results = cursor.fetchall()
    if not results:
        await interaction.followup.send("⚠️ No hay datos disponibles para mostrar la tabla de posiciones.")
        return
    leaderboard_text = ""
    excluded_user_id = 1334910035054297131  # ID del usuario "La Vieja" a excluir
    position = 1
    previous_wins, previous_losses = None, None
    for user_mention, wins, losses in results:
        try:
            user_id = int(user_mention.strip("<@!>"))
        except Exception:
            continue
        if user_id == excluded_user_id:
            continue
        # Ajustar posición solo si el puntaje cambia
        if (wins, losses) != (previous_wins, previous_losses):
            position = leaderboard_text.count("\n") + 1
        leaderboard_text += f"**#{position}** - {wins} Pts. <@{user_id}>\n"
        previous_wins, previous_losses = wins, losses
    embed = discord.Embed(
        title="🏆 Tabla de posiciones:",
        description=leaderboard_text,
        color=discord.Color.gold()
    )
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="help", description="Muestra información sobre los comandos del bot.")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Ayuda del Bot",
        description=(
            "`/start` - Inicia una partida de Tres en Raya.\n"
            "`/start |oponente|` - Inicia una partida contra otro usuario.\n"
            "`/start |dificultad|` - Define la dificultad contra el bot.\n"
            "\n`/stats` - Muestra tus estadísticas.\n"
            "`/stats |usuario|` - Muestra las estadísticas de otro usuario.\n"
            "\n`/leaderboard` - Tabla de posiciones.\n"
            "\n`/help` - Este mensaje de ayuda."
        ),
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    load_partidas()
    load_stats()
    await bot.tree.sync()
    print(f"Bot conectado como {bot.user}")
    activity = discord.Game(name="La Vieja ❎🅾️")
    await bot.change_presence(activity=activity)

webserver.keep_alive()
bot.run(TOKEN)