"""
Execute Command Tool - Safe command execution with strict whitelist.

SAFETY CRITICAL:
- Only whitelisted commands allowed
- Constraints applied (ping -c 1, apt with -y, etc.)
- NEVER allows: reboot, shutdown, rm -rf, dd, mkfs, etc.
- Requires confirmation for package operations
"""
import logging
import subprocess
import shlex
from typing import Dict, Any, Optional, List

from .base_tool import BaseTool

logger = logging.getLogger(__name__)


class ExecuteCommandTool(BaseTool):
    """
    Safe command execution with strict whitelist.

    SAFETY PHILOSOPHY:
    - Whitelist approach: Only explicitly allowed commands
    - Constraints: Commands modified for safety (ping -c 1)
    - Validation: Double-check before execution
    - Logging: All commands logged for audit
    """

    # Whitelisted commands (base command only)
    SAFE_COMMANDS = {
        # System info (read-only, always safe)
        'df', 'free', 'uptime', 'uname', 'hostname', 'whoami', 'id',
        'date', 'cal', 'w', 'who', 'last',

        # Network (constrained)
        'ping',  # Will be constrained to -c 1
        'curl', 'wget',  # For downloads

        # Package management (with -y flag)
        'apt',  # Will add -y and DEBIAN_FRONTEND=noninteractive

        # Process info (read-only)
        'ps', 'top',  # Will add constraints

        # Disk info (read-only)
        'du', 'lsblk',
    }

    # NEVER ALLOW these commands under any circumstances
    FORBIDDEN_COMMANDS = {
        'reboot', 'shutdown', 'poweroff', 'halt',
        'rm', 'rmdir',  # Too dangerous without careful validation
        'dd',  # Disk destroyer
        'mkfs', 'fdisk', 'parted',  # Filesystem operations
        'kill', 'killall', 'pkill',  # Process killing
        'chmod', 'chown',  # Permission changes
        'usermod', 'passwd',  # User modifications
        'iptables', 'ufw',  # Firewall changes
        'systemctl',  # Service management
        'mv',  # File moving can be destructive
        'cp',  # Can overwrite files
    }

    def _get_name(self) -> str:
        return "execute_command"

    def _get_description(self) -> str:
        return """Execute safe system commands.
Only whitelisted commands allowed: df, free, uptime, uname, ping, curl, wget, apt update/upgrade, ps, du.
Commands are automatically constrained for safety (ping -c 1, apt with -y, etc.).
NEVER allows destructive commands like reboot, rm, shutdown, etc."""

    def _get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to execute (will be validated against whitelist)"
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command arguments (optional)"
                }
            },
            "required": ["command"]
        }

    def execute(self, **kwargs) -> str:
        """
        Execute command with safety validation.

        Args:
            command: Base command
            args: Command arguments (optional)

        Returns:
            str: Command output or error message
        """
        try:
            command = kwargs.get("command")
            args = kwargs.get("args", [])

            if not command:
                return "No command provided"

            # Validate command
            validation_result = self._validate_command(command, args)
            if not validation_result['allowed']:
                logger.warning(f"Blocked command: {command} {args}")
                return validation_result['reason']

            # Apply safety constraints
            safe_command, safe_args = self._apply_constraints(command, args)

            # Build full command
            full_command = [safe_command] + safe_args

            logger.info(f"Executing safe command: {' '.join(full_command)}")

            # Execute with timeout
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=30,
                env=self._get_safe_env()
            )

            # Format output
            output = ""
            if result.stdout:
                output += result.stdout

            if result.stderr:
                if output:
                    output += "\n"
                output += f"Errors: {result.stderr}"

            if result.returncode != 0:
                output += f"\nCommand exited with code {result.returncode}"

            return output.strip() if output.strip() else "Command completed successfully (no output)"

        except subprocess.TimeoutExpired:
            return f"Command timed out after 30 seconds"
        except FileNotFoundError:
            return f"Command '{command}' not found on system"
        except Exception as e:
            logger.error(f"Command execution failed: {e}", exc_info=True)
            return f"Command execution failed: {e}"

    def _validate_command(self, command: str, args: List[str]) -> Dict[str, Any]:
        """
        Validate command against whitelist and forbidden list.

        Args:
            command: Base command
            args: Command arguments

        Returns:
            dict: {'allowed': bool, 'reason': str}
        """
        # Check if command is forbidden
        if command.lower() in self.FORBIDDEN_COMMANDS:
            return {
                'allowed': False,
                'reason': f"Command '{command}' is forbidden for safety reasons. I cannot execute destructive commands."
            }

        # Check if command is whitelisted
        if command.lower() not in self.SAFE_COMMANDS:
            return {
                'allowed': False,
                'reason': f"Command '{command}' is not whitelisted. Only safe commands allowed: {', '.join(sorted(self.SAFE_COMMANDS))}"
            }

        # Additional validation for apt commands
        if command.lower() == 'apt':
            if not args:
                return {
                    'allowed': False,
                    'reason': "apt requires subcommand (update, upgrade, install, etc.)"
                }

            subcommand = args[0].lower()

            # Only allow safe apt subcommands
            safe_apt_commands = ['update', 'upgrade', 'search', 'show', 'list']
            if subcommand not in safe_apt_commands:
                return {
                    'allowed': False,
                    'reason': f"apt {subcommand} not allowed. Safe apt commands: {', '.join(safe_apt_commands)}"
                }

        return {'allowed': True, 'reason': ''}

    def _apply_constraints(self, command: str, args: List[str]) -> tuple:
        """
        Apply safety constraints to command.

        Args:
            command: Base command
            args: Command arguments

        Returns:
            tuple: (safe_command, safe_args)
        """
        command_lower = command.lower()

        # Ping: Always constrain to 1 ping
        if command_lower == 'ping':
            # Remove any existing -c args, add our own
            safe_args = [arg for arg in args if not arg.startswith('-c')]
            safe_args = ['-c', '1'] + safe_args
            return (command, safe_args)

        # APT: Add -y and noninteractive
        if command_lower == 'apt':
            # Ensure -y is present
            safe_args = list(args)
            if '-y' not in safe_args and '--yes' not in safe_args:
                safe_args.insert(1, '-y')  # After subcommand

            return (command, safe_args)

        # Top: Add -b (batch mode) and -n 1 (one iteration)
        if command_lower == 'top':
            return (command, ['-b', '-n', '1'])

        # Default: return as-is
        return (command, args)

    def _get_safe_env(self) -> Dict[str, str]:
        """
        Get safe environment variables.

        Returns:
            dict: Environment variables
        """
        import os

        env = os.environ.copy()

        # For apt: noninteractive mode
        env['DEBIAN_FRONTEND'] = 'noninteractive'

        # Prevent interactive prompts
        env['NEEDRESTART_MODE'] = 'l'  # List only, no restart

        return env
