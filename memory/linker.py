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
        Uses a robust placeholder-based masking approach to prevent nested matching.
        """
        # Sort notes by title length descending to match longer titles first (e.g., 'Memory System' before 'Memory')
        sorted_notes = sorted(vault_notes, key=lambda x: len(x["title"]), reverse=True)
        
        # Mask already existing double bracket links
        brackets = []
        def mask_existing(match):
            brackets.append(match.group(0))
            return f"__LINK_BRACKET_PLACEHOLDER_{len(brackets)-1}__"
            
        linked_text = re.sub(r'\[\[.*?\]\]', mask_existing, text)
        
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
                # Match alias on word boundaries
                pattern = rf'\b{re.escape(alias)}\b'
                
                # Replace matching alias with a masked placeholder representing [[title]]
                def replace_and_mask(match):
                    brackets.append(f"[[{title}]]")
                    return f"__LINK_BRACKET_PLACEHOLDER_{len(brackets)-1}__"
                
                linked_text = re.sub(pattern, replace_and_mask, linked_text, flags=re.IGNORECASE)
                
        # Unmask all bracket links
        for i, b in enumerate(brackets):
            linked_text = linked_text.replace(f"__LINK_BRACKET_PLACEHOLDER_{i}__", b)
            
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
