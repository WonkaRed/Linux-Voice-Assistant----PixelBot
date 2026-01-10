"""
System Stats Handler

Provides CPU, RAM, GPU, and process information.

Commands:
- what's my CPU usage?
- how much RAM am I using?
- what's my GPU temperature?
- what process is using the most memory?
"""
import logging
import re
import subprocess
from typing import Optional, List, Tuple

import psutil

from .base import BaseHandler

logger = logging.getLogger(__name__)


class SystemStatsHandler(BaseHandler):
    """Handles system statistics queries."""

    def handle(self, query: str, speak_response: bool = True) -> str:
        """
        Handle system stats query.

        Args:
            query: User query
            speak_response: Whether to speak response

        Returns:
            str: Response text
        """
        try:
            query_lower = query.lower()

            # IMPORTANT: Check SPECIFIC queries FIRST, then fall back to general queries
            # This prevents "CPU temperature" from matching just "CPU" and returning usage

            # 1. Top/Most queries (very specific - check FIRST!)
            if re.search(r'\b(top|most|which\s+one)\b', query_lower):
                if re.search(r'\bmemory|ram\b', query_lower):
                    response = self._get_top_memory_process()
                elif re.search(r'\bcpu\b', query_lower):
                    response = self._get_top_cpu_process()
                else:
                    response = self._get_process_count()

            # 2. Process-related queries (specific)
            elif re.search(r'\bprocess(es)?\b', query_lower):
                if re.search(r'\bmemory|ram\b', query_lower):
                    response = self._get_top_memory_process()
                elif re.search(r'\bcpu\b', query_lower):
                    response = self._get_top_cpu_process()
                elif re.search(r'\b(running|how\s+many|count)\b', query_lower):
                    response = self._get_process_count()
                else:
                    response = self._get_process_count()

            # 3. Temperature queries (specific)
            elif re.search(r'\btemp|temperature\b', query_lower):
                if re.search(r'\bgpu\b', query_lower):
                    response = self._get_gpu_temperature()
                elif re.search(r'\bcpu\b', query_lower):
                    response = self._get_cpu_temperature()
                else:
                    response = self._get_gpu_temperature()  # Default to GPU temp

            # 4. GPU queries (check before CPU/RAM to handle "GPU usage")
            elif re.search(r'\bgpu\b', query_lower):
                response = self._get_gpu_usage()

            # 5. System overview queries
            elif re.search(r'\bsystem|overview|stats\b', query_lower):
                response = self._get_system_overview()

            # 6. General CPU queries
            elif re.search(r'\bcpu\b', query_lower):
                response = self._get_cpu_usage()

            # 7. General RAM/memory queries
            elif re.search(r'\b(ram|memory)\b', query_lower):
                response = self._get_ram_usage()

            else:
                # Default: general system overview
                response = self._get_system_overview()

            # Speak response
            self._speak(response, speak_response)

            return response

        except Exception as e:
            logger.error(f"System stats failed: {e}", exc_info=True)
            error_msg = "Sorry, I couldn't get system stats."
            self._speak(error_msg, speak_response)
            return error_msg

    def _get_cpu_usage(self) -> str:
        """
        Get CPU usage percentage.

        Returns:
            str: Formatted response
        """
        try:
            # Get CPU percentage (1 second interval)
            cpu_percent = psutil.cpu_percent(interval=1)

            # Simple template response (no LLM needed)
            response = f"Your CPU is at {cpu_percent} percent"

            logger.info(f"CPU usage: {cpu_percent}%")
            return response

        except Exception as e:
            logger.error(f"Get CPU usage failed: {e}")
            return "Failed to get CPU usage"

    def _get_cpu_temperature(self) -> str:
        """
        Get CPU temperature.

        Returns:
            str: Formatted response
        """
        try:
            # Try to get CPU temperature from sensors
            temps = psutil.sensors_temperatures()

            if not temps:
                return "CPU temperature monitoring not available"

            # Look for CPU-related temperature sensors
            cpu_temp = None
            for name, entries in temps.items():
                if 'coretemp' in name.lower() or 'cpu' in name.lower() or 'k10temp' in name.lower():
                    for entry in entries:
                        if 'package' in entry.label.lower() or 'tctl' in entry.label.lower():
                            cpu_temp = entry.current
                            break
                    if cpu_temp:
                        break

            if cpu_temp is None and temps:
                # Fallback: use first available temp sensor
                first_sensor = list(temps.values())[0]
                if first_sensor:
                    cpu_temp = first_sensor[0].current

            if cpu_temp:
                response = f"CPU temperature is {int(cpu_temp)} degrees Celsius"
                logger.info(f"CPU temp: {cpu_temp}°C")
                return response
            else:
                return "CPU temperature not available"

        except Exception as e:
            logger.error(f"Get CPU temperature failed: {e}")
            return "Failed to get CPU temperature"

    def _get_ram_usage(self) -> str:
        """
        Get RAM usage.

        Returns:
            str: Formatted response
        """
        try:
            # Get memory info
            mem = psutil.virtual_memory()

            # Convert to GB
            used_gb = mem.used / (1024 ** 3)
            total_gb = mem.total / (1024 ** 3)
            percent = mem.percent

            # Simple template response (no LLM needed)
            response = f"You're using {used_gb:.1f} gigabytes of {total_gb:.1f} gigabytes, that's {percent} percent"

            logger.info(f"RAM usage: {used_gb:.1f}/{total_gb:.1f}GB ({percent}%)")
            return response

        except Exception as e:
            logger.error(f"Get RAM usage failed: {e}")
            return "Failed to get RAM usage"

    def _get_gpu_usage(self) -> str:
        """
        Get GPU usage percentage (NVIDIA only).

        Returns:
            str: Formatted response
        """
        try:
            # Try nvidia-smi
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                gpu_percent = result.stdout.strip()

                # Simple template response (no LLM needed)
                response = f"GPU is at {gpu_percent} percent"

                logger.info(f"GPU usage: {gpu_percent}%")
                return response
            else:
                return "GPU information not available"

        except FileNotFoundError:
            return "GPU monitoring not available. Is nvidia-smi installed?"
        except Exception as e:
            logger.error(f"Get GPU usage failed: {e}")
            return "Failed to get GPU usage"

    def _get_gpu_temperature(self) -> str:
        """
        Get GPU temperature (NVIDIA only).

        Returns:
            str: Formatted response
        """
        try:
            # Try nvidia-smi
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                temp_celsius = result.stdout.strip()

                # Simple template response (no LLM needed)
                response = f"GPU temperature is {temp_celsius} degrees Celsius"

                logger.info(f"GPU temp: {temp_celsius}°C")
                return response
            else:
                return "GPU temperature not available"

        except FileNotFoundError:
            return "GPU monitoring not available. Is nvidia-smi installed?"
        except Exception as e:
            logger.error(f"Get GPU temperature failed: {e}")
            return "Failed to get GPU temperature"

    def _get_top_memory_process(self) -> str:
        """
        Get process using most memory.

        Returns:
            str: Formatted response
        """
        try:
            # Get all processes sorted by memory usage
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
                try:
                    processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Sort by memory
            processes.sort(key=lambda p: p['memory_percent'], reverse=True)

            if processes:
                top_proc = processes[0]
                name = top_proc['name']
                mem_percent = top_proc['memory_percent']

                # Simple template response (no LLM needed)
                response = f"{name} is using the most memory at {mem_percent:.1f} percent"

                logger.info(f"Top memory: {name} ({mem_percent:.1f}%)")
                return response
            else:
                return "No processes found"

        except Exception as e:
            logger.error(f"Get top memory process failed: {e}")
            return "Failed to get process information"

    def _get_top_cpu_process(self) -> str:
        """
        Get process using most CPU.

        Returns:
            str: Formatted response
        """
        try:
            # Get all processes sorted by CPU usage
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Sort by CPU
            processes.sort(key=lambda p: p['cpu_percent'], reverse=True)

            if processes:
                top_proc = processes[0]
                name = top_proc['name']
                cpu_percent = top_proc['cpu_percent']

                # Simple template response (no LLM needed)
                response = f"{name} is using the most CPU at {cpu_percent:.1f} percent"

                logger.info(f"Top CPU: {name} ({cpu_percent:.1f}%)")
                return response
            else:
                return "No processes found"

        except Exception as e:
            logger.error(f"Get top CPU process failed: {e}")
            return "Failed to get process information"

    def _get_process_count(self) -> str:
        """
        Get total process count.

        Returns:
            str: Formatted response
        """
        try:
            count = len(psutil.pids())
            return f"You have {count} processes running"

        except Exception as e:
            logger.error(f"Get process count failed: {e}")
            return "Failed to get process count"

    def _get_system_overview(self) -> str:
        """
        Get general system overview.

        Returns:
            str: Formatted response
        """
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()

            # Simple template response (no LLM needed)
            response = f"System is running at {cpu_percent} percent CPU and {mem.percent} percent RAM"

            return response

        except Exception as e:
            logger.error(f"Get system overview failed: {e}")
            return "Failed to get system overview"
