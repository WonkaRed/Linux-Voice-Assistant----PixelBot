"""
Weather Tool - Get current weather conditions using wttr.in.

Capabilities:
- Get weather by zip code, city+state, or city name
- Defaults to Villa Rica, GA (30180) if no location specified
- Returns current conditions and brief forecast
- Voice-friendly concise output
"""
import logging
import requests
from typing import Dict, Any, Optional

from .base_tool import BaseTool

logger = logging.getLogger(__name__)


class WeatherTool(BaseTool):
    """Get weather information using wttr.in API."""

    # Default location: Villa Rica, GA
    DEFAULT_LOCATION = "30180"

    def _get_name(self) -> str:
        return "get_weather"

    def _get_description(self) -> str:
        return """Get current weather conditions and forecast.
Supports zip codes, city names, city+state combinations.
If no location specified, defaults to Villa Rica, GA (30180).
Use for queries like 'what's the weather', 'weather in Atlanta', 'temperature in 90210', 'what's it like outside', 'temperature outside', 'how's the weather'."""

    def _get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Location (zip code, city name, or city+state). Optional - defaults to Villa Rica GA (30180)"
                }
            },
            "required": []
        }

    def execute(self, **kwargs) -> str:
        """
        Execute weather query.

        Args:
            location: Location string (zip, city, city+state) - optional

        Returns:
            str: Formatted weather information
        """
        try:
            location = kwargs.get("location", self.DEFAULT_LOCATION)

            # Clean up location string
            if location:
                location = location.strip()

            if not location:
                location = self.DEFAULT_LOCATION

            logger.info(f"Weather query for: '{location}'")

            # Fetch weather data using wttr.in JSON API
            weather_data = self._fetch_weather(location)

            if not weather_data:
                return f"Unable to get weather for '{location}'"

            # Format output for voice assistant
            return self._format_weather(weather_data, location)

        except Exception as e:
            logger.error(f"Weather tool failed: {e}", exc_info=True)
            return f"Weather unavailable: {e}"

    def _fetch_weather(self, location: str) -> Optional[Dict[str, Any]]:
        """
        Fetch weather data from wttr.in using JSON format.

        Args:
            location: Location string

        Returns:
            dict: Weather data or None if failed
        """
        try:
            # Best practice: Use format=j1 for structured JSON
            url = f"https://wttr.in/{location}?format=j1"

            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) PixelBot/1.0'
            }

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            return data

        except requests.Timeout:
            logger.error(f"Weather API timeout for '{location}'")
            return None
        except requests.RequestException as e:
            logger.error(f"Weather API request failed: {e}")
            return None
        except ValueError as e:
            logger.error(f"Weather API returned invalid JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching weather: {e}")
            return None

    def _format_weather(self, data: Dict[str, Any], location: str) -> str:
        """
        Format weather data for voice output.

        Args:
            data: Weather data from wttr.in
            location: Location string

        Returns:
            str: Concise weather description
        """
        try:
            # Extract current conditions
            current = data.get('current_condition', [{}])[0]

            # Get temperature (both F and C available)
            temp_f = current.get('temp_F', 'N/A')
            temp_c = current.get('temp_C', 'N/A')
            feels_like_f = current.get('FeelsLikeF', temp_f)

            # Get condition description
            weather_desc = current.get('weatherDesc', [{}])[0].get('value', 'Unknown')

            # Get additional details
            humidity = current.get('humidity', 'N/A')
            wind_mph = current.get('windspeedMiles', 'N/A')
            wind_dir = current.get('winddir16Point', '')

            # Get today's forecast for high/low
            forecast_today = data.get('weather', [{}])[0]
            max_temp_f = forecast_today.get('maxtempF', 'N/A')
            min_temp_f = forecast_today.get('mintempF', 'N/A')

            # Build concise output (optimized for voice)
            output = f"Weather for {location}:\n"
            output += f"Current: {temp_f}°F (feels like {feels_like_f}°F), {weather_desc}\n"
            output += f"Today: High {max_temp_f}°F, Low {min_temp_f}°F\n"
            output += f"Humidity: {humidity}%, Wind: {wind_mph}mph {wind_dir}"

            return output

        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Error parsing weather data: {e}")
            # Fallback to minimal output
            try:
                temp_f = data.get('current_condition', [{}])[0].get('temp_F', 'N/A')
                weather_desc = data.get('current_condition', [{}])[0].get('weatherDesc', [{}])[0].get('value', 'Unknown')
                return f"Weather for {location}: {temp_f}°F, {weather_desc}"
            except:
                return f"Weather data available but couldn't parse for {location}"
