"""
System Stats Tool - Pre-processed system information.

Provides clean, formatted stats for:
- CPU usage and info
- RAM/memory usage
- GPU stats (NVIDIA)
- Disk usage
- Temperature
- Running processes (with filtering)
- System overview
"""
import logging
import subprocess
from typing import Dict, Any, List, Optional

import psutil

from .base import BaseTool

logger = logging.getLogger(__name__)


class SystemStatsTool(BaseTool):
    """Get pre-processed system statistics."""

    @property
    def name(self) -> str:
        return "system_stats"

    @property
    def description(self) -> str:
        return (
            "Get system information like CPU usage, RAM, temperature, disk space, "
            "and running processes. Use stat_type to specify what info you need. "
            "Can filter processes by name or resource usage."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "stat_type": {
                "type": "string",
                "description": "Type of stats to get",
                "enum": ["cpu", "memory", "gpu", "disk", "temperature", "processes", "overview"]
            },
            "process_name": {
                "type": "string",
                "description": "Filter processes by name (optional, case-insensitive)"
            },
            "limit": {
                "type": "integer",
                "description": "Limit number of process results (default 5)"
            }
        }

    @property
    def required_params(self) -> List[str]:
        return ["stat_type"]

    def execute(self, **kwargs) -> str:
        """
        Get system statistics.

        Args:
            stat_type: Type of stats (cpu, memory, gpu, disk, temperature, processes, overview)
            process_name: Optional process name filter
            limit: Max process results

        Returns:
            Formatted stats
        """
        stat_type = kwargs.get("stat_type", "overview")
        process_name = kwargs.get("process_name")
        limit = kwargs.get("limit", 5)

        try:
            if stat_type == "cpu":
                return self._get_cpu()
            elif stat_type == "memory":
                return self._get_memory()
            elif stat_type == "gpu":
                return self._get_gpu()
            elif stat_type == "disk":
                return self._get_disk()
            elif stat_type == "temperature":
                return self._get_temperature()
            elif stat_type == "processes":
                return self._get_processes(process_name, limit)
            elif stat_type == "overview":
                return self._get_overview()
            else:
                return f"ERROR: Unknown stat type '{stat_type}'"

        except Exception as e:
            logger.error(f"System stats failed: {e}", exc_info=True)
            return f"ERROR: Failed to get {stat_type} stats - {e}"

    def _get_cpu(self) -> str:
        """Get CPU statistics."""
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()

        result = f"CPU Usage: {cpu_percent}%\n"
        result += f"CPU Cores: {cpu_count}\n"
        if cpu_freq:
            result += f"Frequency: {cpu_freq.current:.0f} MHz"

        return result

    def _get_memory(self) -> str:
        """Get memory statistics."""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        used_gb = mem.used / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)
        available_gb = mem.available / (1024 ** 3)

        result = f"RAM: {used_gb:.1f} GB / {total_gb:.1f} GB ({mem.percent}%)\n"
        result += f"Available: {available_gb:.1f} GB\n"
        result += f"Swap: {swap.percent}% used"

        return result

    def _get_gpu(self) -> str:
        """Get GPU statistics (NVIDIA)."""
        try:
            # GPU utilization
            usage = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )

            # GPU temperature
            temp = subprocess.run(
                ['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )

            # GPU memory
            mem = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )

            if usage.returncode == 0:
                result = f"GPU Usage: {usage.stdout.strip()}%\n"
                result += f"GPU Temperature: {temp.stdout.strip()}°C\n"

                if mem.returncode == 0:
                    parts = mem.stdout.strip().split(',')
                    if len(parts) == 2:
                        used_mb = int(parts[0].strip())
                        total_mb = int(parts[1].strip())
                        result += f"GPU Memory: {used_mb/1024:.1f} GB / {total_mb/1024:.1f} GB"

                return result
            else:
                return "GPU stats unavailable (nvidia-smi failed)"

        except FileNotFoundError:
            return "GPU stats unavailable (nvidia-smi not found)"
        except Exception as e:
            return f"GPU stats error: {e}"

    def _get_disk(self) -> str:
        """Get disk usage statistics."""
        partitions = psutil.disk_partitions()
        result = "Disk Usage:\n"

        for partition in partitions:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                used_gb = usage.used / (1024 ** 3)
                total_gb = usage.total / (1024 ** 3)

                result += f"\n  {partition.mountpoint}: {used_gb:.1f} GB / {total_gb:.1f} GB ({usage.percent}%)"

            except PermissionError:
                pass

        return result

    def _get_temperature(self) -> str:
        """Get temperature statistics."""
        result = "Temperature:\n"

        # CPU temperature
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    if 'coretemp' in name.lower() or 'cpu' in name.lower() or 'k10temp' in name.lower():
                        for entry in entries:
                            if 'package' in entry.label.lower() or 'tctl' in entry.label.lower() or not entry.label:
                                result += f"  CPU: {int(entry.current)}°C\n"
                                break
                        break
        except:
            pass

        # GPU temperature
        try:
            gpu_temp = subprocess.run(
                ['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=2
            )
            if gpu_temp.returncode == 0:
                result += f"  GPU: {gpu_temp.stdout.strip()}°C"
        except:
            pass

        if result == "Temperature:\n":
            return "Temperature monitoring not available"

        return result.strip()

    def _get_processes(self, process_name: Optional[str] = None, limit: int = 5) -> str:
        """Get running processes, optionally filtered by name."""
        processes = []

        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'memory_percent']):
            try:
                info = proc.info
                mem_mb = info['memory_info'].rss / (1024 ** 2)

                # Filter by name if specified
                if process_name:
                    if process_name.lower() not in info['name'].lower():
                        continue

                processes.append({
                    'name': info['name'],
                    'pid': info['pid'],
                    'cpu': info['cpu_percent'] or 0,
                    'mem_mb': mem_mb,
                    'mem_percent': info['memory_percent'] or 0
                })

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if not processes:
            if process_name:
                return f"No processes found matching '{process_name}'"
            return "No processes found"

        # Sort by memory usage
        processes.sort(key=lambda p: p['mem_mb'], reverse=True)
        processes = processes[:limit]

        if process_name:
            result = f"Processes matching '{process_name}':\n\n"
        else:
            result = f"Top {len(processes)} processes by memory:\n\n"

        for proc in processes:
            result += f"  {proc['name']} (PID {proc['pid']})\n"
            result += f"    RAM: {proc['mem_mb']:.0f} MB ({proc['mem_percent']:.1f}%)\n"
            result += f"    CPU: {proc['cpu']:.1f}%\n"

        return result.strip()

    def _get_overview(self) -> str:
        """Get system overview."""
        cpu_percent = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        result = "System Overview:\n\n"
        result += f"  CPU: {cpu_percent}%\n"
        result += f"  RAM: {mem.percent}% ({mem.used/(1024**3):.1f} GB / {mem.total/(1024**3):.1f} GB)\n"
        result += f"  Disk: {disk.percent}%\n"
        result += f"  Processes: {len(psutil.pids())}"

        return result
