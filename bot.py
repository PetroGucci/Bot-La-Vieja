import discord
import random
import os
from discord.ext import commands
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

# Almacenar partidas activas
partidas = {}

class TicTacToeGame:
    def __init__(self):
        self.tablero = [" "] * 9
        self.jugador_actual = "X"
        self.modo_vs_bot = False
        self.partida_activa = False
        self.jugadores = {}

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
    def __init__(self, game):
        super().__init__(timeout=60)
        self.game = game
        for i in range(9):
            button = Button(style=discord.ButtonStyle.secondary, label=FICHAS[self.game.tablero[i]], row=i // 3)
            button.callback = partial(self.handle_click, index=i)
            self.add_item(button)
    
    async def disable_buttons(self, interaction):
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

    async def check_endgame(self, interaction):
        if self.game.verificar_ganador():
            self.game.partida_activa = False
            await self.disable_buttons(interaction)
            ganador = self.game.jugadores.get(self.game.jugador_actual, "Bot")
            await interaction.message.channel.send(f"🏆 ¡{ganador} ha ganado con {FICHAS[self.game.jugador_actual]}!")
            if not interaction.response.is_done():
                await interaction.response.defer()
            if interaction.channel.id in partidas:
                del partidas[interaction.channel.id]
            return True
        elif " " not in self.game.tablero:
            self.game.partida_activa = False
            await self.disable_buttons(interaction)
            await interaction.message.channel.send("😲 ¡Empate!")
            if not interaction.response.is_done():
                await interaction.response.defer()
            if interaction.channel.id in partidas:
                del partidas[interaction.channel.id]
            return True
        return False

    def evaluate(self, board):
        """Devuelve 10 si gana 'O', -10 si gana 'X', 0 si no hay ganador."""
        wins = [
            (0,1,2), (3,4,5), (6,7,8),
            (0,3,6), (1,4,7), (2,5,8),
            (0,4,8), (2,4,6)
        ]
        for a, b, c in wins:
            if board[a] == board[b] == board[c] and board[a] != " ":
                return 10 if board[a] == "O" else -10
        return 0

    def minimax(self, board, depth, is_maximizing):
        score = self.evaluate(board)
        # Si alguien ha ganado, devolvemos el score
        if score == 10 or score == -10:
            return score
        # Empate
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

    async def bot_move(self, interaction):
        # Usar minimax para encontrar el mejor movimiento
        best_score = -1000
        best_move = None
        board = self.game.tablero[:]  # copia del tablero
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
            await interaction.response.send_message("⚠️ No hay una partida en curso. Usa `!iniciar` para jugar.", ephemeral=True)
            return

        # Bloqueo de clics fuera de turno
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

@bot.command()
async def iniciar(ctx, jugador2: discord.Member = None):
    if ctx.channel.id in partidas:
        await ctx.send("⚠️ Ya hay una partida en curso en este canal. Usa `!reiniciar` si quieres empezar de nuevo.")
        return

    game = TicTacToeGame()
    game.partida_activa = True

    # Si no se especifica jugador2, se juega contra el bot
    if jugador2 is None:
        game.modo_vs_bot = True
        game.jugadores = {"X": ctx.author.mention, "O": bot.user.mention}
    else:
        game.jugadores = {"X": ctx.author.mention, "O": jugador2.mention}

    partidas[ctx.channel.id] = game

    view = TicTacToeView(game)
    embed = discord.Embed(
        title="🎲 ¡Tres en raya!",
        description=f"{game.jugadores['X']} contra {game.jugadores['O']} \n\n🎮 ¡QUE COMIENCE EL JUEGO! 🎮\n\n🔄 Turno de {game.jugadores[game.jugador_actual]} con {FICHAS['X']} !",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=view)

@bot.command()
async def reiniciar(ctx):
    if ctx.channel.id in partidas:
        del partidas[ctx.channel.id]
        await ctx.send("🔄 La partida ha sido reiniciada. Usa `!iniciar` para jugar de nuevo.")
    else:
        await ctx.send("⚠️ No hay ninguna partida activa para reiniciar.")

bot.run(TOKEN)
