import discord
import random
import os
import webserver
import json
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
from dotenv import load_dotenv
from functools import partial

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Configuración del bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Emojis para fichas
FICHAS = {"X": "❎", "O": "🅾️", " ": "⬜"}

# Almacenar partidas activas (clave: ID del mensaje)
partidas = {}

# Almacenar estadísticas de jugadores
stats = {}

def save_partidas():
    with open("partidas.json", "w") as f:
        json.dump(partidas, f, default=lambda o: o.__dict__, indent=4)

def load_partidas():
    global partidas
    if os.path.exists("partidas.json"):
        with open("partidas.json", "r") as f:
            partidas = json.load(f)

def save_stats():
    with open("stats.json", "w") as f:
        json.dump(stats, f, indent=4)

def load_stats():
    global stats
    if os.path.exists("stats.json"):
        with open("stats.json", "r") as f:
            stats = json.load(f)

def update_stats(winner, loser):
    """Actualiza las estadísticas tras una victoria."""
    for player in [winner, loser]:
        if player not in stats:
            stats[player] = {"wins": 0, "losses": 0, "draws": 0}
    stats[winner]["wins"] += 1
    stats[loser]["losses"] += 1
    save_stats()

def update_draw(player1, player2):
    """Actualiza las estadísticas en caso de empate."""
    for player in [player1, player2]:
        if player not in stats:
            stats[player] = {"wins": 0, "losses": 0, "draws": 0}
        stats[player]["draws"] += 1
    save_stats()

class TicTacToeGame:
    def __init__(self, dificultad="dificil"):
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
            update_stats(ganador, perdedor)
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
            update_draw(self.game.jugadores["X"], self.game.jugadores["O"])
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

@bot.tree.command(name="iniciar", description="Inicia una partida de Tres en Raya")
async def iniciar(interaction: discord.Interaction, oponente: discord.Member = None, dificultad: str = None):
    if oponente is not None and oponente.id != bot.user.id and dificultad is not None:
        await interaction.response.send_message("⚠️ El nivel de dificultad solo se puede ajustar al jugar contra el bot. Iniciando partida contra jugador.", ephemeral=True)
        dificultad = None

    if oponente is None or oponente.id == bot.user.id:
        # Jugar contra el bot: se utiliza la dificultad especificada (por defecto "dificil")
        dificultad = dificultad.lower() if dificultad else "dificil"
        if dificultad not in ["facil", "medio", "dificil"]:
            await interaction.response.send_message("⚠️ Dificultad inválida. Usa: facil, medio o dificil.", ephemeral=True)
            return
        game = TicTacToeGame(dificultad=dificultad)
        game.modo_vs_bot = True
        game.jugadores = {"X": interaction.user.mention, "O": bot.user.mention}
    else:
        # Jugar contra otro jugador; se ignora la dificultad
        game = TicTacToeGame()
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
    user = interaction.user.mention
    user_stats = stats.get(user, {"wins": 0, "losses": 0, "draws": 0})
    embed = discord.Embed(
        title="📊 Tus estadísticas",
        description=f"Wins: {user_stats['wins']}\nLosses: {user_stats['losses']}\nDraws: {user_stats['draws']}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    load_partidas()
    load_stats()
    await bot.tree.sync()
    print(f"Bot conectado como {bot.user}")

webserver.keep_alive()
bot.run(TOKEN)
