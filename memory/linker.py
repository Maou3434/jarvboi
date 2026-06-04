import re
from typing import List, Dict, Any, Optional
from memory.vault import ObsidianVault

class ObsidianLinker:
    """Handles auto-linking of entities, alias resolution, and backlinks updates."""
    
    def auto_link_text(
        self,
        text: str,
        vault_notes: List[Dict[str, Any]],
        current_title: Optional[str] = None
    ) -> str:
        """Finds entity names and aliases in the text and wraps them in Obsidian links.
        Merges aliases to their canonical titles, and avoids duplicate/self links.
        """
        # Sort notes by title length descending to match longer titles first (e.g., 'Memory System' before 'Memory')
        sorted_notes = sorted(vault_notes, key=lambda x: len(x["title"]), reverse=True)
        
        linked_text = text
        
        for note in sorted_notes:
            title = note["title"]
            if current_title and title.lower() == current_title.lower():
                continue
                
            # Gather canonical title and aliases
            aliases = [title]
            fm = note.get("metadata", {})
            if "aliases" in fm:
                if isinstance(fm["aliases"], list):
                    aliases.extend(fm["aliases"])
                elif isinstance(fm["aliases"], str):
                    aliases.extend([a.strip() for a in fm["aliases"].split(",")])
                    
            # Remove duplicates from aliases
            aliases = list(dict.fromkeys(aliases))
            
            for alias in aliases:
                # Regex matches alias on word boundaries, but NOT if already in double brackets [[...]]
                # Lookahead and lookbehind assertions to ensure it's not bracketed
                pattern = rf'(?<!\[\[)\b{re.escape(alias)}\b(?!\]\])'
                
                # Replace with the canonical title link [[Title]]
                replacement = f"[[{title}]]"
                
                linked_text = re.sub(pattern, replacement, linked_text, flags=re.IGNORECASE)
                
        return linked_text
        
    def update_backlinks(
        self,
        source_category: str,
        source_title: str,
        target_category: str,
        target_title: str,
        vault: ObsidianVault
    ):
        """Ensures that the target note has a backlink to the source note."""
        if not vault.note_exists(target_category, target_title):
            return
            
        metadata, body = vault.read_note(target_category, target_title)
        
        backlink_str = f"[[{source_title}]]"
        
        # Check if backlink already exists
        if backlink_str in body:
            return
            
        # Parse or append backlink section
        if "## Backlinks" in body:
            # Append to backlinks list
            lines = body.splitlines()
            new_lines = []
            in_backlinks = False
            appended = False
            for line in lines:
                new_lines.append(line)
                if "## Backlinks" in line:
                    in_backlinks = True
                elif in_backlinks and not line.strip() and not appended:
                    new_lines.append(f"- {backlink_str}")
                    appended = True
                    in_backlinks = False
            if not appended:
                new_lines.append(f"- {backlink_str}")
            body = "\n".join(new_lines)
        else:
            body = body.strip() + f"\n\n## Backlinks\n\n- {backlink_str}\n"
            
        vault.write_note(target_category, target_title, metadata, body)
