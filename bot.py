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
    
    def minimax(self, is_maximizing):
        if self.verificar_ganador():
            return -1 if is_maximizing else 1
        elif " " not in self.tablero:
            return 0

        if is_maximizing:
            best_score = -float("inf")
            for i in range(9):
                if self.tablero[i] == " ":
                    self.tablero[i] = "O"
                    score = self.minimax(False)
                    self.tablero[i] = " "
                    best_score = max(score, best_score)
            return best_score
        else:
            best_score = float("inf")
            for i in range(9):
                if self.tablero[i] == " ":
                    self.tablero[i] = "X"
                    score = self.minimax(True)
                    self.tablero[i] = " "
                    best_score = min(score, best_score)
            return best_score

    def mejor_movimiento(self):
        best_score = -float("inf")
        best_move = None
        for i in range(9):
            if self.tablero[i] == " ":
                self.tablero[i] = "O"
                score = self.minimax(False)
                self.tablero[i] = " "
                if score > best_score:
                    best_score = score
                    best_move = i
        return best_move

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
            await interaction.response.defer()
            return True
        elif " " not in self.game.tablero:
            self.game.partida_activa = False
            await self.disable_buttons(interaction)
            await interaction.message.channel.send("😲 ¡Empate!")
            await interaction.response.defer()
            return True
        return False

    async def bot_move(self, interaction):
        movimiento = self.game.mejor_movimiento()
        if movimiento is not None:
            self.game.tablero[movimiento] = "O"
            self.children[movimiento].label = FICHAS["O"]
            self.children[movimiento].disabled = True
            if await self.check_endgame(interaction):
                return
        self.game.jugador_actual = "X"
        await interaction.message.edit(view=self)

    async def handle_click(self, interaction: discord.Interaction, index: int):
        if not self.game.partida_activa:
            await interaction.response.send_message("⚠️ No hay una partida en curso. Usa `!iniciar` para jugar.", ephemeral=True)
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
async def iniciar_bot(ctx):
    game = TicTacToeGame()
    if game.partida_activa:
        await ctx.send("⚠️ Ya hay una partida en curso. Usa `!reiniciar` si quieres empezar de nuevo.")
        return

    game.partida_activa = True
    game.modo_vs_bot = True
    game.jugadores = {"X": ctx.author.mention, "O": bot.user.mention}
    view = TicTacToeView(game)
    embed = discord.Embed(title="🎲 ¡Tres en raya!", description=f"{game.jugadores['X']} contra {game.jugadores['O']} \n\n🎮¡Que comience el juego!🎮\n\n🔄 Turno de {game.jugadores[game.jugador_actual]}", color=discord.Color.blue())
    await ctx.send(embed=embed, view=view)

bot.run(TOKEN)
