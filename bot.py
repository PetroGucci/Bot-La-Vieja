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
            # Eliminamos la partida para permitir iniciar una nueva
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

    async def bot_move(self, interaction):
        posibles_movimientos = [i for i in range(9) if self.game.tablero[i] == " "]
        if posibles_movimientos:
            movimiento = random.choice(posibles_movimientos)
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
