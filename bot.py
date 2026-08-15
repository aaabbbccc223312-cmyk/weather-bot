import os
import re
import logging
import requests

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError(
        "BOT_TOKEN is missing. Add BOT_TOKEN to your Railway Variables."
    )

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# ============================================================
# WEATHER CODE DESCRIPTIONS
# ============================================================

WEATHER_CODES = {
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
    65: "Heavy rain 🌧️",
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

# ============================================================
# CLEAN USER'S LOCATION REQUEST
# ============================================================

def clean_location_text(text: str) -> str:
    """
    Convert natural language into a location search.

    Examples:
        /weather Lagos
        /weather in Lagos
        weather in Lagos
        what is the weather in Lagos
        temperature in London
    """

    text = text.strip()

    # Remove Telegram command
    text = re.sub(r"^/weather(@\w+)?", "", text, flags=re.IGNORECASE)

    # Remove common natural-language phrases
    patterns = [
        r"^\s*what(?:'s| is)?\s+the\s+weather\s+(?:like\s+)?in\s+",
        r"^\s*what(?:'s| is)?\s+the\s+weather\s+in\s+",
        r"^\s*how(?:'s| is)\s+the\s+weather\s+(?:like\s+)?in\s+",
        r"^\s*how\s+is\s+the\s+weather\s+in\s+",
        r"^\s*weather\s+in\s+",
        r"^\s*weather\s+at\s+",
        r"^\s*temperature\s+in\s+",
        r"^\s*temperature\s+at\s+",
        r"^\s*forecast\s+for\s+",
        r"^\s*forecast\s+in\s+",
        r"^\s*weather\s+",
        r"^\s*in\s+",
        r"^\s*at\s+",
    ]

    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Remove question marks and extra punctuation
    text = re.sub(r"[?!.]+$", "", text)

    # Clean extra spaces
    text = re.sub(r"\s+", " ", text).strip()

    return text


# ============================================================
# GEOCODING
# ============================================================

def search_location(location_name: str):
    """
    Search globally for the requested city/state/country.
    """

    url = "https://geocoding-api.open-meteo.com/v1/search"

    params = {
        "name": location_name,
        "count": 10,
        "language": "en",
        "format": "json",
    }

    response = requests.get(
        url,
        params=params,
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    results = data.get("results", [])

    if not results:
        return None

    # Prefer a result with a city/population when possible
    results.sort(
        key=lambda result: (
            result.get("population") or 0
        ),
        reverse=True,
    )

    best = results[0]

    return {
        "name": best.get("name", location_name),
        "country": best.get("country", ""),
        "country_code": best.get("country_code", ""),
        "admin1": best.get("admin1", ""),
        "latitude": best["latitude"],
        "longitude": best["longitude"],
        "timezone": best.get("timezone", "auto"),
    }


# ============================================================
# GET WEATHER
# ============================================================

def get_weather(latitude: float, longitude: float):
    """
    Get current weather from Open-Meteo.
    """

    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "apparent_temperature,"
            "weather_code,"
            "wind_speed_10m,"
            "wind_direction_10m"
        ),
        "timezone": "auto",
    }

    response = requests.get(
        url,
        params=params,
        timeout=15,
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# WEATHER TEXT
# ============================================================

def get_weather_description(code: int) -> str:
    return WEATHER_CODES.get(
        code,
        "Unknown weather"
    )


def wind_direction(degrees: float) -> str:
    """
    Convert wind degrees to N/NE/E/etc.
    """

    directions = [
        "N",
        "NE",
        "E",
        "SE",
        "S",
        "SW",
        "W",
        "NW",
    ]

    index = round(degrees / 45) % 8

    return directions[index]


# ============================================================
# WEATHER MESSAGE
# ============================================================

def build_weather_message(location, weather_data):
    current = weather_data.get("current", {})

    temperature = current.get("temperature_2m", "N/A")
    feels_like = current.get("apparent_temperature", "N/A")
    humidity = current.get("relative_humidity_2m", "N/A")
    wind_speed = current.get("wind_speed_10m", "N/A")
    wind_degrees = current.get("wind_direction_10m", 0)
    weather_code = current.get("weather_code", -1)

    description = get_weather_description(weather_code)
    direction = wind_direction(wind_degrees)

    location_parts = [location["name"]]

    if location.get("admin1"):
        location_parts.append(location["admin1"])

    if location.get("country"):
        location_parts.append(location["country"])

    location_text = ", ".join(
        dict.fromkeys(location_parts)
    )

    return (
        f"🌍 *Weather for {location_text}*\n\n"
        f"🌤️ *Condition:* {description}\n"
        f"🌡️ *Temperature:* {temperature}°C\n"
        f"🤔 *Feels like:* {feels_like}°C\n"
        f"💧 *Humidity:* {humidity}%\n"
        f"💨 *Wind:* {wind_speed} km/h {direction}\n"
        f"🕒 *Timezone:* {location['timezone']}"
    )


# ============================================================
# PROCESS WEATHER REQUEST
# ============================================================

async def process_weather_request(
    update: Update,
    location_text: str,
):
    """
    Main weather-processing function.
    """

    if not location_text:
        await update.message.reply_text(
            "❌ I need a location.\n\n"
            "Try something like:\n"
            "/weather Lagos\n"
            "/weather in Texas\n"
            "/weather New York\n"
            "weather in London"
        )
        return

    status_message = await update.message.reply_text(
        f"🔎 Checking the weather for *{location_text}*...",
        parse_mode="Markdown",
    )

    try:
        # Search for location
        location = search_location(location_text)

        if not location:
            await status_message.edit_text(
                f"❌ I couldn't find *{location_text}*.\n\n"
                "Try using a city, state, or country name.\n\n"
                "Examples:\n"
                "• New York\n"
                "• Texas\n"
                "• California\n"
                "• Lagos\n"
                "• United States",
                parse_mode="Markdown",
            )
            return

        # Get weather
        weather_data = get_weather(
            location["latitude"],
            location["longitude"],
        )

        message = build_weather_message(
            location,
            weather_data,
        )

        await status_message.edit_text(
            message,
            parse_mode="Markdown",
        )

    except requests.RequestException as error:
        logger.error(
            "Weather service error: %s",
            error,
        )

        await status_message.edit_text(
            "⚠️ I couldn't connect to the weather service.\n"
            "Please try again in a moment."
        )

    except Exception as error:
        logger.exception(
            "Unexpected error: %s",
            error,
        )

        await status_message.edit_text(
            "⚠️ Something went wrong.\n"
            "Please try your request again."
        )


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "👋 Hey!\n\n"
        "I'm your worldwide weather bot 🌍🌦️\n\n"
        "Ask me about the weather anywhere in the world.\n\n"
        "Examples:\n"
        "• /weather Lagos\n"
        "• /weather in Brighton\n"
        "• /weather in Texas\n"
        "• /weather New York\n"
        "• weather in London\n"
        "• what is the weather in Tokyo\n\n"
        "Use /help for more information."
    )


# ============================================================
# /HELP
# ============================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "🌦️ *Weather Bot Help*\n\n"
        "I can check weather around the world.\n\n"
        "*Commands:*\n"
        "/weather Lagos\n"
        "/weather in Texas\n"
        "/weather New York\n\n"
        "*Normal messages also work:*\n"
        "weather in London\n"
        "what is the weather in Miami\n"
        "temperature in Tokyo\n\n"
        "🌍 You can ask about cities, states, "
        "regions, and countries.",
        parse_mode="Markdown",
    )


# ============================================================
# /WEATHER
# ============================================================

async def weather_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    Handle /weather requests.
    """

    original_text = update.message.text or ""

    location_text = clean_location_text(
        original_text
    )

    await process_weather_request(
        update,
        location_text,
    )


# ============================================================
# NORMAL TEXT MESSAGES
# ============================================================

async def text_weather(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    Handle normal messages like:

    weather in Miami
    what is the weather in London
    temperature in Tokyo
    """

    text = update.message.text

    if not text:
        return

    lower_text = text.lower().strip()

    # Only treat messages as weather requests
    # if they contain weather-related words.
    weather_keywords = [
        "weather",
        "temperature",
        "forecast",
        "rain",
        "snow",
        "hot",
        "cold",
    ]

    if not any(
        keyword in lower_text
        for keyword in weather_keywords
    ):
        await update.message.reply_text(
            "🌦️ I'm a weather bot.\n\n"
            "Try:\n"
            "weather in London\n"
            "weather in Lagos\n"
            "/weather New York"
        )
        return

    location_text = clean_location_text(text)

    await process_weather_request(
        update,
        location_text,
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.error(
        "Telegram error:",
        exc_info=context.error,
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print("🌍 Weather bot is starting...")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # Commands
    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "weather",
            weather_command,
        )
    )

    # Normal messages
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_weather,
        )
    )

    # Errors
    app.add_error_handler(
        error_handler
    )

    print("✅ Weather bot is running!")

    app.run_polling()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
