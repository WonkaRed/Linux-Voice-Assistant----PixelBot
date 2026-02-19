"""
Notes Tool - Quick note-taking with organized storage.

Features:
- Create, read, list, delete notes
- Organized in ~/.nova/notes/ (never clutters system)
- Timestamped notes
- Search notes by content
"""
import logging
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from .base import BaseTool

logger = logging.getLogger(__name__)

# Notes directory (contained in user's home)
NOTES_DIR = Path.home() / ".nova" / "notes"

# Maximum note size
MAX_NOTE_SIZE = 10000

# Maximum notes to keep
MAX_NOTES = 1000


class NotesTool(BaseTool):
    """Organized note-taking in ~/.nova/notes/."""

    def __init__(self):
        """Initialize notes tool and create directory."""
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Notes directory: {NOTES_DIR}")

    @property
    def name(self) -> str:
        return "notes"

    @property
    def description(self) -> str:
        return (
            "Take and manage notes. Stored safely in ~/.nova/notes/. "
            "Actions: 'add' (create note), 'list' (show notes), 'read' (view note), "
            "'search' (find notes), 'delete' (remove note). "
            "Examples: 'add Buy milk tomorrow', 'list', 'search milk', 'read note-1'"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "action": {
                "type": "string",
                "description": "Action: 'add', 'list', 'read', 'search', 'delete'",
                "enum": ["add", "list", "read", "search", "delete"]
            },
            "content": {
                "type": "string",
                "description": "Note content (for 'add') or search query (for 'search')"
            },
            "note_name": {
                "type": "string",
                "description": "Note filename (for 'read'/'delete', or custom name for 'add')"
            }
        }

    @property
    def required_params(self) -> List[str]:
        return ["action"]

    def execute(self, **kwargs) -> str:
        """
        Execute notes action.

        Args:
            action: add, list, read, search, delete
            content: Note content or search query
            note_name: Note filename

        Returns:
            Result message
        """
        action = kwargs.get("action", "").lower().strip()
        content = kwargs.get("content", "").strip()
        note_name = kwargs.get("note_name", "").strip()

        if action == "add":
            return self._add_note(content, note_name)
        elif action == "list":
            return self._list_notes()
        elif action == "read":
            return self._read_note(note_name or content)
        elif action == "search":
            return self._search_notes(content)
        elif action == "delete":
            return self._delete_note(note_name or content)
        else:
            return "ERROR: Action must be 'add', 'list', 'read', 'search', or 'delete'"

    def _add_note(self, content: str, note_name: str) -> str:
        """Add a new note."""
        if not content:
            return "ERROR: No note content provided"

        if len(content) > MAX_NOTE_SIZE:
            return f"ERROR: Note too long ({len(content)} chars). Max: {MAX_NOTE_SIZE}"

        # Check note count
        existing = list(NOTES_DIR.glob("*.txt"))
        if len(existing) >= MAX_NOTES:
            return f"ERROR: Maximum notes ({MAX_NOTES}) reached. Delete some notes first."

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if note_name:
            # Sanitize custom name
            safe_name = "".join(c for c in note_name if c.isalnum() or c in "-_").lower()
            filename = f"{safe_name}.txt"
        else:
            # Auto-generate from content
            preview = "".join(c for c in content[:30] if c.isalnum() or c == ' ').strip()
            preview = preview.replace(' ', '-').lower()[:20] or "note"
            filename = f"{timestamp}_{preview}.txt"

        filepath = NOTES_DIR / filename

        # Avoid overwriting
        if filepath.exists():
            base = filepath.stem
            counter = 1
            while filepath.exists():
                filepath = NOTES_DIR / f"{base}_{counter}.txt"
                counter += 1

        # Write note
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("-" * 40 + "\n")
                f.write(content)

            logger.info(f"Note saved: {filepath.name}")
            return f"Note saved as '{filepath.name}'"

        except Exception as e:
            logger.error(f"Failed to save note: {e}")
            return f"ERROR: Failed to save note - {e}"

    def _list_notes(self) -> str:
        """List all notes."""
        notes = sorted(NOTES_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)

        if not notes:
            return "No notes found. Use 'add' to create one."

        lines = [f"Notes ({len(notes)} total):"]

        for note in notes[:20]:  # Show latest 20
            # Get first line of content
            try:
                with open(note, 'r', encoding='utf-8') as f:
                    lines_content = f.readlines()
                    # Skip header lines
                    preview = ""
                    for line in lines_content[2:]:  # Skip Created and separator
                        preview = line.strip()[:50]
                        if preview:
                            break
                    preview = preview or "(empty)"
            except:
                preview = "(unreadable)"

            lines.append(f"  - {note.name}: {preview}")

        if len(notes) > 20:
            lines.append(f"  ... and {len(notes) - 20} more")

        return "\n".join(lines)

    def _read_note(self, note_name: str) -> str:
        """Read a note by name."""
        if not note_name:
            return "ERROR: Please specify note name to read"

        # Find note
        filepath = self._find_note(note_name)
        if not filepath:
            return f"ERROR: Note '{note_name}' not found"

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            return f"Note: {filepath.name}\n{'=' * 40}\n{content}"

        except Exception as e:
            return f"ERROR: Failed to read note - {e}"

    def _search_notes(self, query: str) -> str:
        """Search notes by content."""
        if not query:
            return "ERROR: Please provide search query"

        query_lower = query.lower()
        matches = []

        for note in NOTES_DIR.glob("*.txt"):
            try:
                with open(note, 'r', encoding='utf-8') as f:
                    content = f.read()

                if query_lower in content.lower():
                    # Get matching line preview
                    for line in content.split('\n'):
                        if query_lower in line.lower():
                            preview = line.strip()[:60]
                            break
                    else:
                        preview = content[:60].replace('\n', ' ')

                    matches.append((note.name, preview))

            except:
                pass

        if not matches:
            return f"No notes found containing '{query}'"

        lines = [f"Found {len(matches)} note(s) matching '{query}':"]
        for name, preview in matches[:10]:
            lines.append(f"  - {name}: ...{preview}...")

        if len(matches) > 10:
            lines.append(f"  ... and {len(matches) - 10} more")

        return "\n".join(lines)

    def _delete_note(self, note_name: str) -> str:
        """Delete a note by name."""
        if not note_name:
            return "ERROR: Please specify note name to delete"

        filepath = self._find_note(note_name)
        if not filepath:
            return f"ERROR: Note '{note_name}' not found"

        try:
            filepath.unlink()
            logger.info(f"Note deleted: {filepath.name}")
            return f"Note '{filepath.name}' deleted"

        except Exception as e:
            return f"ERROR: Failed to delete note - {e}"

    def _find_note(self, name: str) -> Path:
        """Find a note by name (partial match allowed)."""
        # Exact match first
        exact = NOTES_DIR / name
        if exact.exists():
            return exact

        exact_txt = NOTES_DIR / f"{name}.txt"
        if exact_txt.exists():
            return exact_txt

        # Partial match
        name_lower = name.lower()
        for note in NOTES_DIR.glob("*.txt"):
            if name_lower in note.name.lower():
                return note

        return None
