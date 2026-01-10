"""
System Stats Tool - Advanced system information with filtering.

Capabilities:
- Get processes by memory/CPU usage with thresholds
- Filter by process name
- Get temperature, disk, network stats
- Much more powerful than the simple handler
"""
import logging
import psutil
import subprocess
from typing import Dict, Any, List, Optional

from .base_tool import BaseTool

logger = logging.getLogger(__name__)


class SystemStatsTool(BaseTool):
    """Advanced system statistics with filtering."""

    def _get_name(self) -> str:
        return "get_system_stats"

    def _get_description(self) -> str:
        return """Get detailed system statistics with optional filtering.
Can filter processes by memory/CPU thresholds, get specific process info, temperature, disk usage, etc.
Use this for complex queries like 'what process is using 2GB of RAM' or 'show me processes using more than 50% CPU'."""

    def _get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "stat_type": {
                    "type": "string",
                    "description": "Type of stat to get",
                    "enum": ["cpu", "memory", "gpu", "processes", "disk", "temperature", "network", "overview"]
                },
                "memory_threshold_gb": {
                    "type": "number",
                    "description": "Filter processes using more than this GB of RAM (optional)"
                },
                "cpu_threshold_percent": {
                    "type": "number",
                    "description": "Filter processes using more than this % CPU (optional)"
                },
                "process_name": {
                    "type": "string",
                    "description": "Filter by process name (partial match, case-insensitive, optional)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Limit number of results (default 5)"
                }
            },
            "required": ["stat_type"]
        }

    def execute(self, **kwargs) -> str:
        """
        Execute system stats query.

        Args:
            stat_type: Type of stat
            memory_threshold_gb: Memory filter (optional)
            cpu_threshold_percent: CPU filter (optional)
            process_name: Process name filter (optional)
            limit: Result limit

        Returns:
            str: Formatted stats
        """
        try:
            stat_type = kwargs.get("stat_type")
            memory_threshold_gb = kwargs.get("memory_threshold_gb")
            cpu_threshold_percent = kwargs.get("cpu_threshold_percent")
            process_name = kwargs.get("process_name")
            limit = kwargs.get("limit", 5)

            # CRITICAL FIX: If filters are provided with cpu/memory stat_type,
            # the user wants filtered PROCESSES, not overall stats
            has_filters = (
                memory_threshold_gb is not None or
                cpu_threshold_percent is not None or
                process_name is not None
            )

            if stat_type == "cpu":
                if has_filters:
                    # User wants processes filtered by CPU, not overall CPU stats
                    return self._get_processes(
                        memory_threshold_gb=memory_threshold_gb,
                        cpu_threshold_percent=cpu_threshold_percent,
                        process_name=process_name,
                        limit=limit
                    )
                else:
                    return self._get_cpu_stats()
            elif stat_type == "memory":
                if has_filters:
                    # User wants processes filtered by memory, not overall RAM stats
                    return self._get_processes(
                        memory_threshold_gb=memory_threshold_gb,
                        cpu_threshold_percent=cpu_threshold_percent,
                        process_name=process_name,
                        limit=limit
                    )
                else:
                    return self._get_memory_stats()
            elif stat_type == "processes":
                return self._get_processes(
                    memory_threshold_gb=memory_threshold_gb,
                    cpu_threshold_percent=cpu_threshold_percent,
                    process_name=process_name,
                    limit=limit
                )
            elif stat_type == "gpu":
                return self._get_gpu_stats()
            elif stat_type == "disk":
                return self._get_disk_stats()
            elif stat_type == "temperature":
                return self._get_temperature_stats()
            elif stat_type == "network":
                return self._get_network_stats()
            elif stat_type == "overview":
                return self._get_overview()
            else:
                return f"Unknown stat type: {stat_type}"

        except Exception as e:
            logger.error(f"System stats failed: {e}", exc_info=True)
            return f"Failed to get system stats: {e}"

    def _get_cpu_stats(self) -> str:
        """Get CPU statistics."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()

            stats = f"CPU Usage: {cpu_percent}%\n"
            stats += f"CPU Cores: {cpu_count}\n"
            if cpu_freq:
                stats += f"CPU Frequency: {cpu_freq.current:.0f} MHz"

            return stats

        except Exception as e:
            return f"Failed to get CPU stats: {e}"

    def _get_memory_stats(self) -> str:
        """Get memory statistics."""
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            used_gb = mem.used / (1024 ** 3)
            total_gb = mem.total / (1024 ** 3)
            available_gb = mem.available / (1024 ** 3)

            stats = f"RAM: {used_gb:.1f}GB / {total_gb:.1f}GB ({mem.percent}%)\n"
            stats += f"Available: {available_gb:.1f}GB\n"
            stats += f"Swap: {swap.percent}% used"

            return stats

        except Exception as e:
            return f"Failed to get memory stats: {e}"

    def _get_gpu_stats(self) -> str:
        """Get GPU statistics (NVIDIA)."""
        try:
            # Get GPU usage and temperature
            usage_result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=5
            )

            temp_result = subprocess.run(
                ['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=5
            )

            memory_result = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if usage_result.returncode == 0 and temp_result.returncode == 0:
                gpu_usage = usage_result.stdout.strip()
                gpu_temp = temp_result.stdout.strip()

                stats = f"GPU Usage: {gpu_usage}%\n"
                stats += f"GPU Temp: {gpu_temp}°C\n"

                if memory_result.returncode == 0:
                    mem_parts = memory_result.stdout.strip().split(',')
                    if len(mem_parts) == 2:
                        used_mb = int(mem_parts[0].strip())
                        total_mb = int(mem_parts[1].strip())
                        used_gb = used_mb / 1024
                        total_gb = total_mb / 1024
                        stats += f"GPU Memory: {used_gb:.1f}GB / {total_gb:.1f}GB"

                return stats
            else:
                return "GPU stats unavailable (nvidia-smi failed)"

        except FileNotFoundError:
            return "GPU stats unavailable (nvidia-smi not found)"
        except Exception as e:
            return f"Failed to get GPU stats: {e}"

    def _get_processes(
        self,
        memory_threshold_gb: Optional[float] = None,
        cpu_threshold_percent: Optional[float] = None,
        process_name: Optional[str] = None,
        limit: int = 5
    ) -> str:
        """
        Get process list with optional filtering.

        Args:
            memory_threshold_gb: Filter processes using more than this RAM
            cpu_threshold_percent: Filter processes using more than this CPU
            process_name: Filter by process name
            limit: Max results

        Returns:
            str: Formatted process list
        """
        try:
            processes = []

            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'memory_percent']):
                try:
                    info = proc.info
                    mem_gb = info['memory_info'].rss / (1024 ** 3)

                    # Apply filters
                    if memory_threshold_gb and mem_gb < memory_threshold_gb:
                        continue
                    if cpu_threshold_percent and info['cpu_percent'] < cpu_threshold_percent:
                        continue
                    if process_name and process_name.lower() not in info['name'].lower():
                        continue

                    processes.append({
                        'name': info['name'],
                        'pid': info['pid'],
                        'cpu': info['cpu_percent'],
                        'mem_gb': mem_gb,
                        'mem_percent': info['memory_percent']
                    })

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if not processes:
                filters_desc = []
                if memory_threshold_gb:
                    filters_desc.append(f">{memory_threshold_gb}GB RAM")
                if cpu_threshold_percent:
                    filters_desc.append(f">{cpu_threshold_percent}% CPU")
                if process_name:
                    filters_desc.append(f"name contains '{process_name}'")

                if filters_desc:
                    return f"No processes found matching filters: {', '.join(filters_desc)}"
                else:
                    return "No processes found"

            # Sort by memory usage
            processes.sort(key=lambda p: p['mem_gb'], reverse=True)

            # Limit results
            processes = processes[:limit]

            # Format output
            result = f"Found {len(processes)} process(es):\n\n"
            for proc in processes:
                result += f"• {proc['name']} (PID {proc['pid']})\n"
                result += f"  RAM: {proc['mem_gb']:.2f}GB ({proc['mem_percent']:.1f}%)\n"
                result += f"  CPU: {proc['cpu']:.1f}%\n\n"

            return result.strip()

        except Exception as e:
            return f"Failed to get processes: {e}"

    def _get_disk_stats(self) -> str:
        """Get disk statistics."""
        try:
            partitions = psutil.disk_partitions()
            stats = "Disk Usage:\n\n"

            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    used_gb = usage.used / (1024 ** 3)
                    total_gb = usage.total / (1024 ** 3)

                    stats += f"• {partition.mountpoint}\n"
                    stats += f"  {used_gb:.1f}GB / {total_gb:.1f}GB ({usage.percent}%)\n\n"

                except PermissionError:
                    pass

            return stats.strip()

        except Exception as e:
            return f"Failed to get disk stats: {e}"

    def _get_temperature_stats(self) -> str:
        """Get temperature statistics."""
        try:
            temps = psutil.sensors_temperatures()

            if not temps:
                return "Temperature monitoring not available"

            stats = "Temperature:\n\n"

            # CPU temp
            cpu_temp = None
            for name, entries in temps.items():
                if 'coretemp' in name.lower() or 'cpu' in name.lower() or 'k10temp' in name.lower():
                    for entry in entries:
                        if 'package' in entry.label.lower() or 'tctl' in entry.label.lower():
                            cpu_temp = entry.current
                            break
                    if cpu_temp:
                        break

            if cpu_temp:
                stats += f"• CPU: {int(cpu_temp)}°C\n"

            # GPU temp (NVIDIA)
            try:
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    gpu_temp = result.stdout.strip()
                    stats += f"• GPU: {gpu_temp}°C\n"
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

            return stats.strip()

        except Exception as e:
            return f"Failed to get temperature: {e}"

    def _get_network_stats(self) -> str:
        """Get network statistics."""
        try:
            net_io = psutil.net_io_counters()

            sent_mb = net_io.bytes_sent / (1024 ** 2)
            recv_mb = net_io.bytes_recv / (1024 ** 2)

            stats = "Network (since boot):\n"
            stats += f"• Sent: {sent_mb:.1f}MB\n"
            stats += f"• Received: {recv_mb:.1f}MB"

            return stats

        except Exception as e:
            return f"Failed to get network stats: {e}"

    def _get_overview(self) -> str:
        """Get system overview."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            stats = "System Overview:\n\n"
            stats += f"• CPU: {cpu_percent}%\n"
            stats += f"• RAM: {mem.percent}%\n"
            stats += f"• Disk: {disk.percent}%\n"
            stats += f"• Processes: {len(psutil.pids())}"

            return stats

        except Exception as e:
            return f"Failed to get overview: {e}"
