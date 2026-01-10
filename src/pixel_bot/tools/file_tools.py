"""
File Tools - Search and read files safely.

Tools:
- search_files: Find files by name/pattern
- read_file: Read file contents
"""
import logging
import os
import glob
from typing import Dict, Any, List
from pathlib import Path

from .base_tool import BaseTool

logger = logging.getLogger(__name__)


class SearchFilesTool(BaseTool):
    """Search for files by name or pattern."""

    def _get_name(self) -> str:
        return "search_files"

    def _get_description(self) -> str:
        return """Search for files by name or pattern.
Use this when the user asks to find files like 'find my config files' or 'where is my .bashrc'.
Returns list of matching files with paths."""

    def _get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "File name or pattern to search for (supports wildcards like *.txt)"
                },
                "directory": {
                    "type": "string",
                    "description": "Directory to search in (default: user home directory)"
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Search recursively in subdirectories (default: true)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default 10)"
                }
            },
            "required": ["pattern"]
        }

    def execute(self, **kwargs) -> str:
        """
        Search for files.

        Args:
            pattern: File pattern
            directory: Search directory (optional)
            recursive: Search recursively (default True)
            limit: Result limit (default 10)

        Returns:
            str: Formatted file list
        """
        try:
            pattern = kwargs.get("pattern")
            directory = kwargs.get("directory")
            recursive = kwargs.get("recursive", True)
            limit = kwargs.get("limit", 10)

            if not pattern:
                return "No search pattern provided"

            # Default to home directory
            if not directory:
                directory = str(Path.home())

            # Validate directory exists
            if not os.path.isdir(directory):
                return f"Directory not found: {directory}"

            logger.info(f"Searching for '{pattern}' in '{directory}' (recursive: {recursive})")

            # Build search pattern
            if recursive:
                search_pattern = os.path.join(directory, '**', pattern)
            else:
                search_pattern = os.path.join(directory, pattern)

            # Search files
            matches = glob.glob(search_pattern, recursive=recursive)

            # Limit results
            matches = matches[:limit]

            if not matches:
                return f"No files found matching '{pattern}' in {directory}"

            # Format output
            output = f"Found {len(matches)} file(s) matching '{pattern}':\n\n"

            for match in matches:
                # Get file info
                try:
                    stat = os.stat(match)
                    size = stat.st_size

                    # Format size
                    if size < 1024:
                        size_str = f"{size}B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f}KB"
                    else:
                        size_str = f"{size / (1024 * 1024):.1f}MB"

                    output += f"• {match}\n  ({size_str})\n\n"

                except OSError:
                    output += f"• {match}\n\n"

            return output.strip()

        except Exception as e:
            logger.error(f"File search failed: {e}", exc_info=True)
            return f"File search failed: {e}"


class ReadFileTool(BaseTool):
    """Read file contents."""

    # Max file size to read (1MB)
    MAX_FILE_SIZE = 1024 * 1024

    def _get_name(self) -> str:
        return "read_file"

    def _get_description(self) -> str:
        return """Read contents of a file.
Use this when the user asks to read a file or show file contents.
Returns file content (limited to first 1KB for large files)."""

    def _get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to file to read"
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum lines to read (default 50)"
                }
            },
            "required": ["file_path"]
        }

    def execute(self, **kwargs) -> str:
        """
        Read file contents.

        Args:
            file_path: Path to file
            max_lines: Max lines to read (default 50)

        Returns:
            str: File contents
        """
        try:
            file_path = kwargs.get("file_path")
            max_lines = kwargs.get("max_lines", 50)

            if not file_path:
                return "No file path provided"

            # Validate file exists
            if not os.path.exists(file_path):
                return f"File not found: {file_path}"

            if not os.path.isfile(file_path):
                return f"Not a file: {file_path}"

            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size > self.MAX_FILE_SIZE:
                return f"File too large ({file_size / (1024*1024):.1f}MB). Maximum size: 1MB"

            logger.info(f"Reading file: {file_path}")

            # Try to read as text
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= max_lines:
                            lines.append(f"\n... (truncated at {max_lines} lines)")
                            break
                        lines.append(line.rstrip())

                    content = '\n'.join(lines)

                    if not content.strip():
                        return f"File is empty: {file_path}"

                    output = f"Contents of {file_path}:\n\n{content}"
                    return output

            except UnicodeDecodeError:
                return f"File appears to be binary (cannot read as text): {file_path}"

        except PermissionError:
            return f"Permission denied: {file_path}"
        except Exception as e:
            logger.error(f"File read failed: {e}", exc_info=True)
            return f"File read failed: {e}"
