import os
import re
from typing import Dict, Any, Tuple, Optional, List

class ObsidianVault:
    """Manages files and directories in the Obsidian Memories Vault, handling 
    YAML frontmatter and conflict detection formatting.
    """
    
    def __init__(self, vault_dir: Optional[str] = None):
        if vault_dir is None:
            # Default to workspace relative 'Obsidian/Memories'
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.vault_dir = os.path.join(project_root, "Obsidian", "Memories")
        else:
            self.vault_dir = vault_dir
            
        self.categories = ["People", "Projects", "Concepts", "Daily", "Meetings", "Procedures", "Archive"]
        self.initialize_vault()
        
    def initialize_vault(self):
        """Creates the vault directory and all category subfolders if they do not exist."""
        os.makedirs(self.vault_dir, exist_ok=True)
        for cat in self.categories:
            os.makedirs(os.path.join(self.vault_dir, cat), exist_ok=True)
            
    def get_note_path(self, category: str, title: str) -> str:
        """Returns the full path to a note under a category, enforcing markdown extension."""
        # Sanitize filename
        safe_title = re.sub(r'[\\/*?:"<>|]', '_', title)
        return os.path.join(self.vault_dir, category, f"{safe_title}.md")
        
    def note_exists(self, category: str, title: str) -> bool:
        """Checks if a note exists under a category."""
        return os.path.exists(self.get_note_path(category, title))
        
    def read_note(self, category: str, title: str) -> Tuple[Dict[str, Any], str]:
        """Reads a note, parsing its YAML frontmatter and markdown body."""
        path = self.get_note_path(category, title)
        if not os.path.exists(path):
            return {}, ""
            
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            
        return self.parse_note_content(content)
        
    def write_note(self, category: str, title: str, metadata: Dict[str, Any], body: str):
        """Writes a note, serializing its frontmatter and body."""
        path = self.get_note_path(category, title)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        full_content = self.serialize_note_content(metadata, body)
        with open(path, "w", encoding="utf-8") as f:
            f.write(full_content)
            
    def parse_note_content(self, content: str) -> Tuple[Dict[str, Any], str]:
        """Splits note content into metadata (frontmatter) and markdown body."""
        content = content.strip()
        if not content.startswith("---"):
            return {}, content
            
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}, content
            
        fm_text = parts[1]
        body = parts[2].strip()
        
        metadata = {}
        for line in fm_text.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            
            # Type conversions
            if v.replace('.', '', 1).isdigit():
                metadata[k] = float(v) if '.' in v else int(v)
            elif v.lower() == "true":
                metadata[k] = True
            elif v.lower() == "false":
                metadata[k] = False
            else:
                metadata[k] = v
                
        return metadata, body
        
    def serialize_note_content(self, metadata: Dict[str, Any], body: str) -> str:
        """Constructs a raw note string combining YAML frontmatter and body."""
        if not metadata:
            return body.strip() + "\n"
            
        lines = ["---"]
        for k, v in metadata.items():
            lines.append(f"{k}: {v}")
        lines.append("---")
        lines.append(body.strip())
        return "\n".join(lines) + "\n"
        
    def list_all_notes(self) -> List[Dict[str, Any]]:
        """Scans all folders in the vault recursively and returns a list of notes with metadata."""
        notes = []
        for cat in self.categories:
            cat_dir = os.path.join(self.vault_dir, cat)
            if not os.path.exists(cat_dir):
                continue
            for entry in os.scandir(cat_dir):
                if entry.is_file() and entry.name.endswith(".md"):
                    title = entry.name[:-3]
                    path = entry.path
                    rel_path = os.path.join(cat, entry.name)
                    mtime = entry.stat().st_mtime
                    try:
                        metadata, body = self.read_note(cat, title)
                        notes.append({
                            "title": title,
                            "category": cat,
                            "path": path,
                            "rel_path": rel_path.replace("\\", "/"),
                            "mtime": mtime,
                            "metadata": metadata,
                            "body": body
                        })
                    except Exception:
                        pass
        return notes
        
    def add_conflict(self, category: str, title: str, old_fact: str, new_fact: str):
        """Formats and appends conflicting information to a note without overwriting."""
        metadata, body = self.read_note(category, title)
        
        conflict_block = f"\n\n## Conflicting Information\n\n- {old_fact} (older)\n- {new_fact} (newer)\n\nStatus: unresolved\n"
        
        # Check if Conflicting Information section already exists
        if "## Conflicting Information" in body:
            # Append new conflict items to the existing section
            body = body.strip() + f"\n- {old_fact} (older)\n- {new_fact} (newer)\n"
        else:
            body = body.strip() + conflict_block
            
        self.write_note(category, title, metadata, body)
