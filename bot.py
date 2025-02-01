import discord
import random
import os
from discord.ext import commands
from discord.ui import View, Button
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Configuración del bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Variables del juego
tablero = [" "] * 9
jugador_actual = "X"
modo_vs_bot = False
partida_activa = False
jugadores = {}

# Emojis para fichas
fichas = {"X": "❌", "O": "⭕", " ": "⬜"}

# Función para verificar el ganador
def verificar_ganador():
    combinaciones_ganadoras = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],
        [0, 3, 6], [1, 4, 7], [2, 5, 8],
        [0, 4, 8], [2, 4, 6]
    ]
    for combo in combinaciones_ganadoras:
        a, b, c = combo
        if tablero[a] == tablero[b] == tablero[c] and tablero[a] != " ":
            return True
    return False

# Clase para la interfaz de los botones
class TicTacToeView(View):
    def __init__(self):
        super().__init__(timeout=60)
    
    async def disable_buttons(self, interaction):
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

    async def check_endgame(self, interaction):
        global partida_activa
        
        if verificar_ganador():
            partida_activa = False
            await self.disable_buttons(interaction)
            ganador = jugadores[jugador_actual] if jugador_actual in jugadores else "Bot"
            await interaction.message.channel.send(f"🏆 ¡{ganador} ha ganado con {fichas[jugador_actual]}!")
            return True
        elif " " not in tablero:
            partida_activa = False
            await self.disable_buttons(interaction)
            await interaction.message.channel.send("😲 ¡Empate!")
            return True
        return False

    async def bot_move(self, interaction):
        global jugador_actual
        
        posibles_movimientos = [i for i in range(9) if tablero[i] == " "]
        if posibles_movimientos:
            movimiento = random.choice(posibles_movimientos)
            tablero[movimiento] = "O"
            self.children[movimiento].label = fichas["O"]
            self.children[movimiento].disabled = True
            
            if await self.check_endgame(interaction):
                return

        jugador_actual = "X"
        await interaction.message.edit(view=self)

    async def handle_click(self, interaction: discord.Interaction, index: int):
        global jugador_actual, partida_activa

        if not partida_activa:
            await interaction.response.send_message("⚠️ No hay una partida en curso. Usa `!iniciar` para jugar.", ephemeral=True)
            return

        if tablero[index] != " ":
            await interaction.response.send_message("❌ Esa casilla ya está ocupada.", ephemeral=True)
            return

        tablero[index] = jugador_actual
        self.children[index].label = fichas[jugador_actual]
        self.children[index].disabled = True

        if await self.check_endgame(interaction):
            return

        jugador_actual = "O" if jugador_actual == "X" else "X"

        await interaction.response.edit_message(view=self)

        if modo_vs_bot and jugador_actual == "O":
            await self.bot_move(interaction)

@bot.command()
async def iniciar(ctx, jugador2: discord.Member = None):
    global tablero, jugador_actual, modo_vs_bot, partida_activa, jugadores

    if partida_activa:
        await ctx.send("⚠️ Ya hay una partida en curso. Usa `!reiniciar` si quieres empezar de nuevo.")
        return

    if jugador2 is None:
        await ctx.send("⚠️ Necesitas especificar al segundo jugador para una partida entre jugadores.")
        return

    tablero = [" "] * 9
    jugador_actual = "X"
    modo_vs_bot = False
    partida_activa = True
    jugadores = {"X": ctx.author.mention, "O": jugador2.mention}
    
    mensaje = f"{jugadores['X']} contra {jugadores['O']} 🎮 ¡Que comience la partida!"

    view = TicTacToeView()
    for i in range(9):
        button = Button(style=discord.ButtonStyle.secondary, label=fichas[tablero[i]], row=i // 3)
        button.callback = lambda interaction, index=i: view.handle_click(interaction, index)
        view.add_item(button)

    embed = discord.Embed(title="🎲 ¡Tres en raya!", description=f"{mensaje}\n\n🔄 Turno de {jugadores[jugador_actual]}", color=discord.Color.blue())
    await ctx.send(embed=embed, view=view)

@bot.command()
async def iniciar_bot(ctx):
    global tablero, jugador_actual, modo_vs_bot, partida_activa, jugadores

    if partida_activa:
        await ctx.send("⚠️ Ya hay una partida en curso. Usa `!reiniciar` si quieres empezar de nuevo.")
        return

    tablero = [" "] * 9
    jugador_actual = "X"
    modo_vs_bot = True
    partida_activa = True
    jugadores = {"X": ctx.author.mention, "O": "🤖 Bot"}
    
    mensaje = f"{jugadores['X']} contra {jugadores['O']} 🤖 ¡Que comience la partida!"

    view = TicTacToeView()
    for i in range(9):
        button = Button(style=discord.ButtonStyle.secondary, label=fichas[tablero[i]], row=i // 3)
        button.callback = lambda interaction, index=i: view.handle_click(interaction, index)
        view.add_item(button)

    embed = discord.Embed(title="🎲 ¡Tres en raya!", description=f"{mensaje}\n\n🔄 Turno de {jugadores[jugador_actual]}", color=discord.Color.blue())
    await ctx.send(embed=embed, view=view)

@bot.command()
async def reiniciar(ctx):
    global partida_activa
    if not partida_activa:
        await ctx.send("⚠️ No hay una partida en curso. Usa `!iniciar` para empezar.")
        return
    partida_activa = False
    await ctx.send("🔄 La partida ha sido reiniciada. Usa `!iniciar` para jugar de nuevo.")

bot.run(TOKEN)
