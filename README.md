# Bot-La-Vieja

Bot-La-Vieja es un bot de Discord desarrollado en Python. Este bot está diseñado para proporcionar diversas funcionalidades y mejorar la experiencia de los usuarios en un servidor de Discord.

## Instalación

Sigue los siguientes pasos para instalar y configurar el bot en tu máquina local.

### Clonar el repositorio

Primero, clona el repositorio desde GitHub:

```bash
git clone https://github.com/PetroGucci/Bot-La-Vieja.git
cd Bot-La-Vieja
```

### Crear un entorno virtual

Es recomendable crear un entorno virtual para evitar conflictos con otras librerías y proyectos. A continuación, se explica cómo crear y activar un entorno virtual en diferentes plataformas.

#### Windows

```bash
pip install virtualenv
virtualenv venv
.\venv\Scripts\activate
```

#### MacOS y Linux

```bash
pip install virtualenv
virtualenv venv
source venv/bin/activate
```

### Instalar dependencias

Una vez que el entorno virtual esté activado, instala las dependencias necesarias:

```bash
pip install discord.py
pip install python-dotenv
pip install -r requirements.txt
```

## Uso

Después de instalar las dependencias, puedes ejecutar el bot con el siguiente comando:

```bash
python bot.py
```

Asegúrate de configurar correctamente el archivo `.env` con tus credenciales y tokens necesarios para que el bot funcione correctamente.

¡Y eso es todo! Ahora deberías tener el bot funcionando en tu servidor de Discord.
