import os
import logging
import requests

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing.")

# =========================
# LOGGING
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================
# WEATHER FUNCTIONS
# =========================

def get_location(city: str):
    """Find latitude/longitude for a city."""
    url = "https://geocoding-api.open-meteo.com/v1/search"

    params = {
        "name": city,
        "count": 1,
        "language": "en",
        "format": "json",
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    if not data.get("results"):
        return None

    location = data["results"][0]

    return {
        "name": location.get("name", city),
        "country": location.get("country", ""),
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "timezone": location.get("timezone", "auto"),
    }


def get_weather(latitude: float, longitude: float):
    """Get current weather for coordinates."""
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "apparent_temperature,"
            "weather_code,"
            "wind_speed_10m"
        ),
        "timezone": "auto",
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    return response.json()


def weather_description(code: int) -> str:
    """Convert Open-Meteo weather code into readable text."""

    descriptions = {
        0: "Clear sky ☀️",
        1: "Mainly clear 🌤️",
        2: "Partly cloudy ⛅",
        3: "Overcast ☁️",
        45: "Fog 🌫️",
        48: "Depositing rime fog 🌫️",
        51: "Light drizzle 🌦️",
        53: "Moderate drizzle 🌦️",
        55: "Dense drizzle 🌧️",
        56: "Light freezing drizzle 🧊",
        57: "Dense freezing drizzle 🧊",
        61: "Slight rain 🌦️",
        63: "Moderate rain 🌧️",
        65: "Heavy rain ⛈️",
        66: "Light freezing rain 🧊",
        67: "Heavy freezing rain 🧊",
        71: "Slight snow ❄️",
        73: "Moderate snow ❄️",
        75: "Heavy snow ❄️",
        77: "Snow grains ❄️",
        80: "Slight rain showers 🌦️",
        81: "Moderate rain showers 🌧️",
        82: "Violent rain showers ⛈️",
        85: "Slight snow showers 🌨️",
        86: "Heavy snow showers 🌨️",
        95: "Thunderstorm ⛈️",
        96: "Thunderstorm with slight hail ⛈️",
        99: "Thunderstorm with heavy hail ⛈️",
    }

    return descriptions.get(code, "Unknown weather")


# =========================
# TELEGRAM COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start."""

    await update.message.reply_text(
        "👋 Hey!\n\n"
        "I'm your weather bot 🌦️\n\n"
        "Use:\n"
        "/weather Lagos\n"
        "/weather Abuja\n"
        "/weather London\n\n"
        "You can also use /help."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help."""

    await update.message.reply_text(
        "🌦️ Weather Bot Help\n\n"
        "Use the command below:\n\n"
        "/weather <city>\n\n"
        "Example:\n"
        "/weather Lagos"
    )


async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /weather CITY."""

    if not context.args:
        await update.message.reply_text(
            "❌ Please enter a city.\n\n"
            "Example:\n"
            "/weather Lagos"
        )
        return

    city = " ".join(context.args)

    # Tell user we're working
    status_message = await update.message.reply_text(
        f"🔎 Checking the weather for {city}..."
    )

    try:
        # Get coordinates
        location = get_location(city)

        if not location:
            await status_message.edit_text(
                f"❌ I couldn't find **{city}**.\n\n"
                "Try another city name.",
                parse_mode="Markdown",
            )
            return

        # Get weather
        weather_data = get_weather(
            location["latitude"],
            location["longitude"],
        )

        current = weather_data["current"]

        temperature = current["temperature_2m"]
        feels_like = current["apparent_temperature"]
        humidity = current["relative_humidity_2m"]
        wind_speed = current["wind_speed_10m"]
        weather_code = current["weather_code"]

        description = weather_description(weather_code)

        message = (
            f"🌍 *Weather for {location['name']}, {location['country']}*\n\n"
            f"🌡️ *Temperature:* {temperature}°C\n"
            f"🤔 *Feels like:* {feels_like}°C\n"
            f"☁️ *Condition:* {description}\n"
            f"💧 *Humidity:* {humidity}%\n"
            f"💨 *Wind:* {wind_speed} km/h\n"
            f"🕒 *Timezone:* {location['timezone']}"
        )

        await status_message.edit_text(
            message,
            parse_mode="Markdown",
        )

    except requests.RequestException as error:
        logger.error("Weather API error: %s", error)

        await status_message.edit_text(
            "⚠️ Sorry, I couldn't connect to the weather service right now."
        )

    except Exception as error:
        logger.exception("Unexpected error: %s", error)

        await status_message.edit_text(
            "⚠️ Something went wrong while getting the weather."
        )


# =========================
# ERROR HANDLER
# =========================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log errors."""

    logger.error(
        "Exception while processing update:",
        exc_info=context.error,
    )


# =========================
# MAIN
# =========================

def main():
    """Start the Telegram bot."""

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("weather", weather))

    # Error handling
    app.add_error_handler(error_handler)

    print("🌦️ Weather bot is running...")

    # Start bot using Telegram long polling
    app.run_polling()


if __name__ == "__main__":
    main()
