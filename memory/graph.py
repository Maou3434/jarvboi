import re
import networkx as nx
from typing import List, Dict, Any, Set, Optional
from memory.vault import ObsidianVault

class ObsidianGraph:
    """Extracts and manages a lightweight NetworkX relationship graph derived
    solely from Obsidian note links.
    """
    
    def __init__(self):
        self.graph = nx.DiGraph()
        
    def rebuild_graph(self, vault: ObsidianVault):
        """Scans the vault notes, builds nodes, parses links, and constructs directed edges."""
        self.graph.clear()
        notes = vault.list_all_notes()
        
        # 1. Add all notes as nodes first
        for note in notes:
            title = note["title"]
            self.graph.add_node(
                title, 
                category=note["category"], 
                path=note["path"]
            )
            
        # 2. Parse brackets and add edges
        for note in notes:
            source = note["title"]
            body = note["body"]
            
            # Find all [[target]] brackets
            raw_links = re.findall(r'\[\[(.*?)\]\]', body)
            for link in raw_links:
                # Resolve link formats: [[Target#Section|Alias]], [[Target|Alias]], [[Target#Section]]
                target = link.split("|")[0].split("#")[0].strip()
                if not target:
                    continue
                    
                # We can draw edges even to target nodes that don't exist yet in the vault
                if not self.graph.has_node(target):
                    self.graph.add_node(target, category="External", path="")
                    
                self.graph.add_edge(source, target)
                
    def get_connected_notes(self, title: str) -> List[str]:
        """Returns all incoming and outgoing connected note titles for a given node (1-hop proximity)."""
        if not self.graph.has_node(title):
            return []
            
        # nx.all_neighbors returns predecessors and successors
        neighbors = set(nx.all_neighbors(self.graph, title))
        
        # Filter out self-loops or empty/external nodes if they have no details
        return [n for n in neighbors if n != title]
        
    def get_shortest_path_distance(self, source: str, target: str) -> Optional[int]:
        """Calculates distance between two notes, helpful for graph proximity scoring."""
        if not self.graph.has_node(source) or not self.graph.has_node(target):
            return None
        try:
            # Undirected path distance for proximity
            return nx.shortest_path_length(self.graph.to_undirected(), source, target)
        except nx.NetworkXNoPath:
            return None
