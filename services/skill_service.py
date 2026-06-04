import os
import sys
import re
import json
import importlib.util
from typing import List, Dict, Any, Optional
from config.settings import Settings
from utils.logger import logger
from tools.registry import registry

# Custom robust YAML parser in case PyYAML is not installed
def parse_yaml_fallback(text: str) -> Dict[str, Any]:
    """Fallback parser for YAML frontmatter using a simple indentation state machine."""
    result = {}
    lines = text.split("\n")
    current_key = None
    param_lines = []
    
    for line in lines:
        if not line.strip() or line.strip().startswith("#"):
            continue
            
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        
        if indent == 0:
            if param_lines and current_key == "parameters":
                try:
                    result["parameters"] = parse_indented_yaml(param_lines)
                except Exception as e:
                    logger.warning(f"[SkillService] Fallback parameter parser failed: {e}")
                    result["parameters"] = {"type": "object", "properties": {}, "required": []}
                param_lines = []
                
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip()
                if val:
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    # Check for basic array or boolean
                    if val.startswith("[") and val.endswith("]"):
                        val = [x.strip().strip('"').strip("'") for x in val[1:-1].split(",") if x.strip()]
                    elif val.lower() == "true":
                        val = True
                    elif val.lower() == "false":
                        val = False
                    result[key] = val
                else:
                    current_key = key
                    result[key] = {}
        else:
            if current_key == "parameters":
                param_lines.append(line)
                
    if param_lines and current_key == "parameters":
        try:
            result["parameters"] = parse_indented_yaml(param_lines)
        except Exception as e:
            logger.warning(f"[SkillService] Fallback parameter parser failed at EOF: {e}")
            result["parameters"] = {"type": "object", "properties": {}, "required": []}
            
    return result

def parse_indented_yaml(lines: List[str]) -> Dict[str, Any]:
    """Helper to parse indented YAML lines into a nested dictionary."""
    if not lines:
        return {}
        
    result = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        
        if ":" in stripped:
            key, val = stripped.split(":", 1)
            key = key.strip()
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
                
            if val:
                if val.lower() == "true":
                    val = True
                elif val.lower() == "false":
                    val = False
                elif val.lower() == "null" or val.lower() == "none":
                    val = None
                elif val.isdigit():
                    val = int(val)
                elif val.replace(".", "", 1).isdigit():
                    val = float(val)
                elif val.startswith("[") and val.endswith("]"):
                    val = [x.strip().strip('"').strip("'") for x in val[1:-1].split(",") if x.strip()]
                result[key] = val
                i += 1
            else:
                # Accumulate nested lines with greater indentation
                nested_lines = []
                j = i + 1
                while j < len(lines):
                    next_stripped = lines[j].lstrip()
                    next_indent = len(lines[j]) - len(next_stripped)
                    if next_indent > indent:
                        nested_lines.append(lines[j])
                        j += 1
                    else:
                        break
                result[key] = parse_indented_yaml(nested_lines)
                i = j
        else:
            i += 1
    return result


# --- Lightweight Jaccard Similarity for local skill searches ---
NOISY_WORDS = {"what", "was", "that", "is", "the", "a", "an", "and", "user", "jarvis", "to", "of", "in", "it", "for", "on", "with", "as", "at", "by", "this", "there", "they", "we", "you", "i", "me", "my", "your", "he", "she", "it"}

def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    return text

def compute_jaccard(text1: str, text2: str) -> float:
    c1 = clean_text(text1)
    c2 = clean_text(text2)
    words1 = set(w for w in c1.split() if w not in NOISY_WORDS)
    words2 = set(w for w in c2.split() if w not in NOISY_WORDS)
    
    if not words1: words1 = set(c1.split())
    if not words2: words2 = set(c2.split())
    if not words1 or not words2:
        return 0.0
    return len(words1.intersection(words2)) / len(words1.union(words2))


class SkillService:
    """Discovers, parses, imports, and manages custom skills saved in skills/ directory."""
    
    def __init__(self, event_bus=None, skills_dir: Optional[str] = None, db_service=None):
        self.event_bus = event_bus
        
        # Lazy import of DbService
        from services.db_service import DbService
        self.db_service = db_service or DbService()
        
        if skills_dir is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.skills_dir = os.path.join(project_root, "skills")
        else:
            self.skills_dir = skills_dir
            
        os.makedirs(self.skills_dir, exist_ok=True)
        self.skills: Dict[str, Dict[str, Any]] = {}
        
        # Load and scan skills
        self.reload_skills()
        
    def reload_skills(self):
        """Scans the skills folder and loads all available skills, syncing from SQLite DB if active."""
        self.skills.clear()
        
        # 1. Load from filesystem first
        if os.path.exists(self.skills_dir):
            for item in os.listdir(self.skills_dir):
                item_path = os.path.join(self.skills_dir, item)
                if os.path.isdir(item_path):
                    skill_md_path = os.path.join(item_path, "SKILL.md")
                    if os.path.exists(skill_md_path):
                        try:
                            skill_meta = self._load_skill_file(skill_md_path, item)
                            if skill_meta:
                                self.skills[skill_meta["name"]] = skill_meta
                                # Check for tool.py and dynamically import
                                tool_py_path = os.path.join(item_path, "tool.py")
                                if os.path.exists(tool_py_path):
                                    self._import_tool_py(skill_meta["name"], tool_py_path)
                        except Exception as e:
                            logger.error(f"[SkillService] Error loading skill folder '{item}': {e}")
                            
        # 2. Sync from database if enabled
        if Settings.USE_SQLITE:
            try:
                db_skills = self.db_service.get_skills()
                for skill in db_skills:
                    name = skill["name"]
                    skill_folder = os.path.join(self.skills_dir, name)
                    os.makedirs(skill_folder, exist_ok=True)
                    
                    skill_md_path = os.path.join(skill_folder, "SKILL.md")
                    if not os.path.exists(skill_md_path):
                        # Reconstruct the YAML frontmatter
                        params = skill.get("parameters") or {"type": "object", "properties": {}, "required": []}
                        frontmatter = {
                            "name": name,
                            "description": skill["description"],
                            "category": skill["category"],
                            "parameters": params
                        }
                        try:
                            import yaml
                            yaml_text = yaml.dump(frontmatter, default_flow_style=False)
                        except Exception:
                            # simple fallback serializer
                            yaml_text = f"name: {name}\ndescription: \"{skill['description']}\"\ncategory: {skill['category']}\n"
                            
                        with open(skill_md_path, "w", encoding="utf-8") as f:
                            f.write(f"---\n{yaml_text}---\n\n{skill['markdown_content']}\n")
                            
                    tool_py_path = os.path.join(skill_folder, "tool.py")
                    if skill.get("python_code") and not os.path.exists(tool_py_path):
                        with open(tool_py_path, "w", encoding="utf-8") as f:
                            f.write(skill["python_code"])
                            
                    # Load metadata
                    self.skills[name] = {
                        "name": name,
                        "description": skill["description"],
                        "category": skill["category"],
                        "parameters": skill.get("parameters") or {"type": "object", "properties": {}, "required": []},
                        "body": skill["markdown_content"],
                        "folder_path": skill_folder
                    }
                    
                    # Import dynamic tool
                    if os.path.exists(tool_py_path):
                        self._import_tool_py(name, tool_py_path)
            except Exception as e:
                logger.error(f"[SkillService] Error syncing skills from SQLite database: {e}")
                            
        logger.info(f"[SkillService] Loaded {len(self.skills)} custom skills (filesystem + DB).")
        
    def _load_skill_file(self, filepath: str, folder_name: str) -> Optional[Dict[str, Any]]:
        """Parses SKILL.md file and returns parsed metadata."""
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Parse frontmatter
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
        if not frontmatter_match:
            logger.warning(f"[SkillService] SKILL.md in '{folder_name}' has invalid frontmatter structure.")
            return None
            
        frontmatter_text = frontmatter_match.group(1)
        markdown_body = frontmatter_match.group(2).strip()
        
        # Parse YAML frontmatter
        meta = {}
        try:
            import yaml
            meta = yaml.safe_load(frontmatter_text)
        except ImportError:
            meta = parse_yaml_fallback(frontmatter_text)
        except Exception as e:
            logger.warning(f"[SkillService] PyYAML failed to parse frontmatter: {e}. Trying fallback parser...")
            meta = parse_yaml_fallback(frontmatter_text)
            
        if not meta or "name" not in meta:
            logger.warning(f"[SkillService] Skill in '{folder_name}' is missing required 'name' field in frontmatter.")
            return None
            
        return {
            "name": meta["name"],
            "description": meta.get("description", ""),
            "category": meta.get("category", "automation"),
            "parameters": meta.get("parameters", {"type": "object", "properties": {}, "required": []}),
            "body": markdown_body,
            "folder_path": os.path.dirname(filepath)
        }
        
    def _import_tool_py(self, skill_name: str, file_path: str):
        """Dynamically imports the python file to trigger its tool registration."""
        try:
            module_name = f"skills.{skill_name}.tool"
            
            # Clean from sys.modules to allow clean re-import
            if module_name in sys.modules:
                del sys.modules[module_name]
                
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                logger.info(f"[SkillService] Dynamic python tool for skill '{skill_name}' imported and registered.")
        except Exception as e:
            logger.error(f"[SkillService] Failed to dynamically load python code for skill '{skill_name}': {e}")
            
    def retrieve_relevant_skills(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """Finds matching skills using word overlap (Jaccard similarity)."""
        scored_skills = []
        for skill in self.skills.values():
            # Compute similarity against name, description and body
            sim_name = compute_jaccard(query, skill["name"]) * 1.5
            sim_desc = compute_jaccard(query, skill["description"])
            sim_body = compute_jaccard(query, skill["body"]) * 0.5
            score = max(sim_name, sim_desc, sim_body)
            
            if score > 0.08:  # threshold
                scored_skills.append((score, skill))
                
        scored_skills.sort(key=lambda x: x[0], reverse=True)
        return [skill for _, skill in scored_skills[:top_k]]
        
    def create_skill(self, name: str, description: str, parameters: Dict[str, Any], python_code: Optional[str], markdown_content: str) -> bool:
        """Writes skill files to disk and dynamically registers them."""
        # Ensure clean name (alphanumeric and underscores)
        clean_name = re.sub(r'[^\w]', '_', name.lower().strip())
        skill_dir = os.path.join(self.skills_dir, clean_name)
        os.makedirs(skill_dir, exist_ok=True)
        
        # 1. Format frontmatter
        frontmatter = {
            "name": clean_name,
            "description": description,
            "category": "automation" if python_code else "instructions",
            "parameters": parameters or {"type": "object", "properties": {}, "required": []}
        }
        
        try:
            import yaml
            frontmatter_yaml = yaml.dump(frontmatter, default_flow_style=False)
        except Exception:
            # Fallback simple serializer if yaml package is missing
            lines = [
                f"name: {frontmatter['name']}",
                f"description: \"{frontmatter['description']}\"",
                f"category: {frontmatter['category']}"
            ]
            lines.append("parameters:")
            params = frontmatter["parameters"]
            lines.append(f"  type: {params.get('type', 'object')}")
            lines.append("  properties:")
            for p_name, p_val in params.get("properties", {}).items():
                lines.append(f"    {p_name}:")
                lines.append(f"      type: {p_val.get('type', 'string')}")
                lines.append(f"      description: \"{p_val.get('description', '')}\"")
            req = params.get("required", [])
            lines.append(f"  required: [{', '.join(req)}]")
            frontmatter_yaml = "\n".join(lines)
            
        # 2. Write SKILL.md
        skill_md_content = f"---\n{frontmatter_yaml}---\n\n{markdown_content}\n"
        skill_md_path = os.path.join(skill_dir, "SKILL.md")
        with open(skill_md_path, "w", encoding="utf-8") as f:
            f.write(skill_md_content)
            
        # 3. Write tool.py if python code exists
        if python_code and python_code.strip():
            # Validate python code syntax before writing
            try:
                compile(python_code, "<string>", "exec")
            except Exception as e:
                logger.error(f"[SkillService] Python syntax validation failed for skill '{clean_name}': {e}")
                return False
                
            tool_py_path = os.path.join(skill_dir, "tool.py")
            with open(tool_py_path, "w", encoding="utf-8") as f:
                f.write(python_code)
                
            # Import immediately
            self._import_tool_py(clean_name, tool_py_path)
            
        # Reload skill meta into registry
        skill_meta = self._load_skill_file(skill_md_path, clean_name)
        if skill_meta:
            self.skills[clean_name] = skill_meta
            
        # Write to SQLite DB if active
        if Settings.USE_SQLITE:
            try:
                self.db_service.add_skill(
                    name=clean_name,
                    description=description,
                    category="automation" if python_code else "instructions",
                    parameters=parameters,
                    markdown_content=markdown_content,
                    python_code=python_code
                )
            except Exception as e:
                logger.error(f"[SkillService] Failed to save skill '{clean_name}' to SQLite: {e}")
            
        if self.event_bus:
            self.event_bus.publish("skill_created", {"name": clean_name, "description": description})
            
        return True
