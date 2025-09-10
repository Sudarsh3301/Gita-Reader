import streamlit as st
import streamlit.components.v1 as components
import networkx as nx
from pyvis.network import Network
import tempfile
import os
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
import json
import base64
from io import StringIO
import pandas as pd

# Color scheme for different node types and schools
NODE_COLORS = {
    'verse': '#FF6B6B',      # Coral red
    'concept': '#4ECDC4',     # Teal
    'commentary': '#45B7D1',  # Blue
    'query': '#96CEB4',       # Light green
    'school': '#9C27B0',      # Purple
    'author': '#8B4513'       # Brown
}

SCHOOL_COLORS = {
    'adi_shankara': '#8E44AD',      # Purple
    'ramanuja': '#E67E22',          # Orange
    'madhva': '#27AE60',            # Green
    'sridhara': '#F39C12',          # Gold
    'dhanpati': '#E74C3C',          # Red
    'vedantadeshika': '#3498DB',    # Light blue
    'vallabha': '#9B59B6',          # Violet
    'chaitanya': '#1ABC9C',         # Turquoise
    'default': '#95A5A6'            # Gray
}

class GitaGraphVisualizer:
    def __init__(self, kg, search_engine):
        self.kg = kg
        self.search_engine = search_engine
        self.graph = nx.Graph()
        self.node_positions = {}
        self.current_query = ""
        
    def build_knowledge_graph(self, limit_nodes: int = 500):
        """Build NetworkX graph from knowledge graph data"""
        self.graph.clear()

        # Strategy: Add ALL nodes that are referenced by edges to avoid missing node issues
        nodes_to_add = set()

        # Strategy: Prioritize nodes by importance and edge connectivity
        node_importance = {}

        if hasattr(self.kg, 'edges') and self.kg.edges:
            # Count how many edges each node participates in
            for edge in self.kg.edges:
                node_importance[edge.source] = node_importance.get(edge.source, 0) + 1
                node_importance[edge.target] = node_importance.get(edge.target, 0) + 1
                # Add ALL nodes referenced by edges to ensure no missing nodes
                nodes_to_add.add(edge.source)
                nodes_to_add.add(edge.target)

            # If we have too many nodes, prioritize by importance
            if len(nodes_to_add) > limit_nodes:
                sorted_nodes = sorted(node_importance.items(), key=lambda x: x[1], reverse=True)
                nodes_to_add = set([node for node, count in sorted_nodes[:limit_nodes]])
                # st.info(f"Limited to top {limit_nodes} most connected nodes out of {len(node_importance)} total")
            # else:
            #     # st.info(f"Adding all {len(nodes_to_add)} nodes referenced by edges")

        # If no edges, fall back to adding sample nodes
        if not nodes_to_add:
            # Add a sample of each type
            verse_sample = list(self.kg.verses.keys())[:50]
            concept_sample = list(self.kg.concepts.keys())[:100]
            commentary_sample = list(self.kg.commentaries.keys())[:50]

            for verse_id in verse_sample:
                nodes_to_add.add(f"verse:{verse_id}")
            for concept_term in concept_sample:
                nodes_to_add.add(f"concept:{concept_term}")
            for commentary_id in commentary_sample:
                nodes_to_add.add(f"commentary:{commentary_id}")

            st.info(f"No edges found, using sample nodes: {len(nodes_to_add)} total")

        node_count = 0
        nodes_added_by_type = {'verse': 0, 'concept': 0, 'commentary': 0, 'school': 0, 'author': 0}

        # Add verse nodes that are in our set
        for verse_id, verse in self.kg.verses.items():
            verse_node_id = f"verse:{verse_id}"
            if verse_node_id in nodes_to_add:
                self.graph.add_node(
                    verse_node_id,
                    type='verse',
                    title=f"Chapter {verse.chapter}, Verse {verse.verse}",
                    label=f"BG {verse.chapter}.{verse.verse}",
                    translations=verse.translations,
                    transliteration=verse.transliteration,
                    shloka=verse.shloka,
                    word_meaning=verse.word_meaning,
                    size=15,
                    color=NODE_COLORS['verse']
                )
                node_count += 1
                nodes_added_by_type['verse'] += 1
            
        # Add concept nodes that are in our set
        concept_nodes_in_set = 0
        for concept_term, concept in self.kg.concepts.items():
            concept_node_id = f"concept:{concept_term}"
            if concept_node_id in nodes_to_add:
                concept_nodes_in_set += 1
                self.graph.add_node(
                    concept_node_id,
                    type='concept',
                    title=f"Concept: {concept_term}",
                    label=concept_term[:20] + "..." if len(concept_term) > 20 else concept_term,
                    meaning=concept.meaning,
                    size=10,
                    color=NODE_COLORS['concept']
                )
                node_count += 1
                nodes_added_by_type['concept'] += 1

        # st.info(f"Found {concept_nodes_in_set} concept nodes in edge set out of {len(self.kg.concepts)} total concepts")
                    
        # Add commentary nodes that are in our set
        for commentary_id, commentary in self.kg.commentaries.items():
            commentary_node_id = f"commentary:{commentary_id}"
            if commentary_node_id in nodes_to_add and commentary.text.strip():
                school_color = SCHOOL_COLORS.get(commentary.school, SCHOOL_COLORS['default'])

                self.graph.add_node(
                    commentary_node_id,
                    type='commentary',
                    title=f"Commentary by {commentary.school}",
                    label=f"{commentary.school[:15]}...",
                    school=commentary.school,
                    author=commentary.original_author,
                    text=commentary.text[:200] + "..." if len(commentary.text) > 200 else commentary.text,
                    size=8,
                    color=school_color
                )
                node_count += 1
                nodes_added_by_type['commentary'] += 1

        # Add school nodes that are in our set
        for school in self.kg.schools:
            school_node_id = f"school:{school}"
            if school_node_id in nodes_to_add:
                self.graph.add_node(
                    school_node_id,
                    type='school',
                    title=f"School: {school}",
                    label=school[:15] + "..." if len(school) > 15 else school,
                    size=12,
                    color=SCHOOL_COLORS.get(school, SCHOOL_COLORS['default'])
                )
                node_count += 1
                nodes_added_by_type['school'] += 1

        # Add author nodes that are in our set
        for author in self.kg.authors:
            author_node_id = f"author:{author}"
            if author_node_id in nodes_to_add:
                self.graph.add_node(
                    author_node_id,
                    type='author',
                    title=f"Author: {author}",
                    label=author[:15] + "..." if len(author) > 15 else author,
                    size=8,
                    color=NODE_COLORS.get('author', '#8B4513')  # Brown color for authors
                )
                node_count += 1
                nodes_added_by_type['author'] += 1

        # st.info(f"Nodes added by type: {nodes_added_by_type}")

        # Add edges from the knowledge graph edge list
        kg_edges = getattr(self.kg, 'edges', [])
        # st.info(f"Knowledge graph has {len(kg_edges)} edges")
        # st.info(f"Knowledge graph attributes: {[attr for attr in dir(self.kg) if not attr.startswith('_')]}")

        # if hasattr(self.kg, 'edges') and self.kg.edges:
        #     # st.info(f"Adding {len(self.kg.edges)} edges from knowledge graph")
        # else:
        #     st.warning("No edges found in knowledge graph - using legacy edge system")

        edges_added = 0
        missing_sources = []
        missing_targets = []

        for edge in kg_edges:
            if self.graph.has_node(edge.source) and self.graph.has_node(edge.target):
                # Map edge types to visual properties
                edge_props = {
                    'MENTIONS': {'color': '#4CAF50', 'width': 2, 'style': 'solid'},
                    'COMMENTS_ON': {'color': '#2196F3', 'width': 3, 'style': 'solid'},
                    'BELONGS_TO_SCHOOL': {'color': '#FF9800', 'width': 2, 'style': 'dashed'},
                    'WRITTEN_BY': {'color': '#9C27B0', 'width': 2, 'style': 'dotted'},
                    'SUBSTITUTED_BY': {'color': '#F44336', 'width': 2, 'style': 'dotted'}
                }

                props = edge_props.get(edge.edge_type, {'color': '#666666', 'width': 1, 'style': 'solid'})

                self.graph.add_edge(
                    edge.source,
                    edge.target,
                    type=edge.edge_type,
                    weight=props['width'],
                    color=props['color'],
                    style=props['style'],
                    attributes=edge.attributes
                )
                edges_added += 1
            else:
                # Count missing nodes for summary
                if not self.graph.has_node(edge.source):
                    missing_sources.append(edge.source)
                if not self.graph.has_node(edge.target):
                    missing_targets.append(edge.target)

        # st.info(f"Successfully added {edges_added} edges out of {len(kg_edges)} total edges")

        # Show summary of missing nodes
        if missing_sources or missing_targets:
            unique_missing_sources = set(missing_sources)
            unique_missing_targets = set(missing_targets)
            st.warning(f"Missing nodes: {len(unique_missing_sources)} unique source nodes, {len(unique_missing_targets)} unique target nodes")

            # Show sample missing nodes
            if unique_missing_targets:
                sample_missing = list(unique_missing_targets)[:5]
                st.warning(f"Sample missing target nodes: {sample_missing}")
        else:
            st.success("All edge nodes found in graph!")

        # Fallback: Add legacy edges if no new edges were added
        if self.graph.number_of_edges() == 0:
            st.info("Using legacy edge system as fallback")

            # Legacy concept to verse edges
            for concept_term, concept in self.kg.concepts.items():
                concept_node_id = f"concept:{concept_term}"
                if self.graph.has_node(concept_node_id):
                    for verse_id in concept.mentioned_in:
                        verse_node_id = f"verse:{verse_id}"
                        if self.graph.has_node(verse_node_id):
                            self.graph.add_edge(concept_node_id, verse_node_id,
                                              type='mentions', weight=1)

            # Legacy commentary to verse edges
            for commentary_id, commentary in self.kg.commentaries.items():
                commentary_node_id = f"commentary:{commentary_id}"
                if self.graph.has_node(commentary_node_id):
                    verse_node_id = f"verse:{commentary.verse_id}"
                    if self.graph.has_node(verse_node_id):
                        self.graph.add_edge(commentary_node_id, verse_node_id,
                                          type='comments_on', weight=1)

        st.info(f"Built knowledge graph with {self.graph.number_of_nodes()} nodes and {self.graph.number_of_edges()} edges")
        
    def get_subgraph_around_nodes(self, center_nodes: List[str], max_hops: int = 2, max_nodes: int = 50) -> nx.Graph:
        """Extract subgraph centered around specific nodes"""
        if not center_nodes or not self.graph.nodes():
            return nx.Graph()
            
        subgraph_nodes = set()
        
        # Add center nodes
        for node in center_nodes:
            if node in self.graph:
                subgraph_nodes.add(node)
        
        # Add neighbors within max_hops
        for hop in range(max_hops):
            if len(subgraph_nodes) >= max_nodes:
                break
                
            current_nodes = list(subgraph_nodes)
            for node in current_nodes:
                if len(subgraph_nodes) >= max_nodes:
                    break
                    
                neighbors = list(self.graph.neighbors(node))
                for neighbor in neighbors[:5]:  # Limit neighbors per node
                    if len(subgraph_nodes) >= max_nodes:
                        break
                    subgraph_nodes.add(neighbor)
        
        return self.graph.subgraph(subgraph_nodes).copy()
    
    def create_verse_centric_visualization(self, search_results: List, max_nodes: int = 50) -> str:
        """Create interactive visualization centered around search results"""
        if not search_results:
            return ""
            
        # Get center nodes from search results
        center_nodes = []
        query_paths = []
        
        for result in search_results[:3]:  # Limit to top 3 results
            verse_node_id = f"verse:{result.verse.id}"
            center_nodes.append(verse_node_id)
            
            # Track query paths for highlighting
            for path in result.provenance_path:
                query_paths.append(path)
        
        # Create subgraph
        subgraph = self.get_subgraph_around_nodes(center_nodes, max_hops=2, max_nodes=max_nodes)
        
        if not subgraph.nodes():
            return ""
        
        # Create Pyvis network
        net = Network(height="400px", width="100%", bgcolor="#1e1e1e", font_color="white")
        net.set_options("""
        {
          "physics": {
            "enabled": true,
            "stabilization": {"iterations": 100}
          },
          "layout": {
            "improvedLayout": true
          },
          "interaction": {
            "hover": true,
            "tooltipDelay": 300
          }
        }
        """)
        
        # Add nodes to Pyvis
        for node_id, data in subgraph.nodes(data=True):
            node_type = data.get('type', 'unknown')
            
            # Create tooltip
            tooltip = self._create_node_tooltip(node_id, data)
            
            # Highlight center nodes
            if node_id in center_nodes:
                size = data.get('size', 10) + 5
                color = '#FFD700'  # Gold for search results
            else:
                size = data.get('size', 10)
                color = data.get('color', '#95A5A6')
            
            net.add_node(
                node_id,
                label=data.get('label', node_id),
                title=tooltip,
                size=size,
                color=color,
                font={'size': 12}
            )
        
        # Add edges
        for source, target, data in subgraph.edges(data=True):
            edge_type = data.get('type', 'connected')
            edge_color = '#666666'
            
            if edge_type == 'mentions':
                edge_color = '#4ECDC4'
            elif edge_type == 'comments_on':
                edge_color = '#45B7D1'
                
            net.add_edge(source, target, color=edge_color, width=2)
        
        # Generate HTML
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.html', delete=False) as f:
            temp_file_path = f.name

        try:
            net.save_graph(temp_file_path)
            with open(temp_file_path, 'r', encoding='utf-8') as file:
                html_content = file.read()
        finally:
            # Safe file deletion with retry
            try:
                os.unlink(temp_file_path)
            except (PermissionError, FileNotFoundError):
                # If we can't delete immediately, schedule for later cleanup
                import atexit
                atexit.register(lambda: self._safe_delete(temp_file_path))

        return html_content

    def _safe_delete(self, file_path: str):
        """Safely delete a file with retry logic"""
        import time
        for attempt in range(3):
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                break
            except (PermissionError, FileNotFoundError):
                if attempt < 2:
                    time.sleep(0.1)  # Wait a bit and retry
                # If all attempts fail, just ignore - the temp file will be cleaned up by the OS eventually

    def _create_node_tooltip(self, node_id: str, data: dict) -> str:
        """Create detailed tooltip for graph nodes"""
        node_type = data.get('type', 'unknown')
        
        if node_type == 'verse':
            tooltip = f"<b>{data.get('title', 'Verse')}</b><br>"
            if 'shloka' in data:
                tooltip += f"<i>{data['shloka'][:50]}...</i><br>"
            if 'translations' in data and 'en' in data['translations']:
                tooltip += f"{data['translations']['en'][:100]}..."
                
        elif node_type == 'concept':
            tooltip = f"<b>{data.get('title', 'Concept')}</b><br>"
            if 'meaning' in data:
                tooltip += f"{data['meaning'][:100]}..."
                
        elif node_type == 'commentary':
            tooltip = f"<b>{data.get('title', 'Commentary')}</b><br>"
            if 'author' in data:
                tooltip += f"Author: {data['author']}<br>"
            if 'text' in data:
                tooltip += f"{data['text'][:100]}..."
        else:
            tooltip = f"<b>{node_id}</b>"
            
        return tooltip
    

    
    def get_path_trace(self, provenance_paths: List[str]) -> List[Dict]:
        """Convert provenance paths to structured breadcrumb data"""
        traces = []
        for path in provenance_paths:
            # Parse path string like "Query → Concept(dharma) → Verse(2:31)"
            steps = [step.strip() for step in path.split('→')]
            trace = {
                'path': path,
                'steps': steps,
                'length': len(steps)
            }
            traces.append(trace)
        return traces

def render_graph_visualization_panel(kg, search_results, current_query=""):
    """Main function to render graph visualizations in Streamlit"""
    if not search_results:
        return
        
    visualizer = GitaGraphVisualizer(kg, None)
    
    # Build knowledge graph if needed
    if visualizer.graph.number_of_nodes() == 0:
        with st.spinner("Building knowledge graph..."):
            visualizer.build_knowledge_graph(limit_nodes=1000)  # Increased limit
    
    # Graph Visualization Section
    st.subheader("🌐 Knowledge Graph Visualization")
    
    # Controls
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        # Simplified to only show Verse-Centric Canvas
        st.info("📊 Interactive Knowledge Graph - Verse-Centric View")
    
    with col2:
        max_nodes = st.slider("Max Nodes", 20, 100, 50)
    
    
    # Render Verse-Centric Canvas visualization
    html_content = visualizer.create_verse_centric_visualization(
        search_results, max_nodes=max_nodes
    )

    if html_content:
        # Display breadcrumb traces
        st.subheader("📍 Search Provenance")
        for i, result in enumerate(search_results[:3], 1):
            with st.expander(f"Result {i} Paths", expanded=i==1):
                traces = visualizer.get_path_trace(result.provenance_path)
                for trace in traces:
                    # Create breadcrumb display
                    breadcrumb = " → ".join([
                        f"<span style='background-color: #4ECDC4; padding: 2px 6px; border-radius: 3px; margin: 2px;'>{step}</span>"
                        for step in trace['steps']
                    ])
                    st.markdown(breadcrumb, unsafe_allow_html=True)

        # Display interactive graph - larger size for tab view
        st.subheader("📊 Interactive Knowledge Graph")
        components.html(html_content, height=600, scrolling=False)
    
    # Legend

def render_node_details_panel(kg, selected_node_id: str = None):
    """Render detailed information panel for selected graph node"""
    if not selected_node_id:
        st.info("👆 Click on a graph node to view details")
        return
    
    node_type, node_key = selected_node_id.split(':', 1)
    
    st.subheader(f"📋 Node Details: {selected_node_id}")
    
    if node_type == 'verse':
        verse = kg.verses.get(node_key)
        if verse:
            st.markdown(f"**Chapter {verse.chapter}, Verse {verse.verse}**")
            st.markdown(f"**Sanskrit:** {verse.shloka}")
            
            if verse.transliteration:
                st.markdown(f"**Transliteration:** {verse.transliteration}")
            
            if 'en' in verse.translations:
                st.markdown(f"**English:** {verse.translations['en']}")
            
            if verse.word_meaning:
                st.markdown("**Word Meanings:**")
                for term, meaning in list(verse.word_meaning.items())[:5]:
                    st.markdown(f"• **{term}:** {meaning}")
                    
            # Export button
            if st.button("📋 Copy Verse Text", key=f"copy_{node_key}"):
                verse_text = f"BG {verse.chapter}.{verse.verse}\n{verse.shloka}\n{verse.translations.get('en', '')}"
                st.text_area("Verse Text (Ctrl+A, Ctrl+C to copy):", verse_text, height=100)
    
    elif node_type == 'concept':
        concept = kg.concepts.get(node_key)
        if concept:
            st.markdown(f"**Concept:** {concept.term}")
            st.markdown(f"**Meaning:** {concept.meaning}")
            st.markdown(f"**Mentioned in {len(concept.mentioned_in)} verses**")
            
            if concept.mentioned_in:
                st.markdown("**Related Verses:**")
                for verse_id in concept.mentioned_in[:5]:
                    verse = kg.verses.get(verse_id)
                    if verse:
                        st.markdown(f"• Chapter {verse.chapter}, Verse {verse.verse}")
    
    elif node_type == 'commentary':
        commentary = kg.commentaries.get(node_key)
        if commentary:
            st.markdown(f"**School:** {commentary.school}")
            st.markdown(f"**Status:** {commentary.status}")
            
            if commentary.original_author:
                st.markdown(f"**Author:** {commentary.original_author}")
            
            if commentary.substitute_author:
                st.markdown(f"**Substitute Author:** {commentary.substitute_author}")
            
            st.markdown("**Commentary Text:**")
            st.markdown(commentary.text[:500] + "..." if len(commentary.text) > 500 else commentary.text)

    elif node_type == 'school':
        st.markdown(f"**School:** {node_key}")
        # Show commentaries from this school
        school_commentaries = [c for c in kg.commentaries.values() if c.school == node_key]
        st.markdown(f"**Total Commentaries:** {len(school_commentaries)}")

        if school_commentaries:
            st.markdown("**Sample Commentaries:**")
            for commentary in school_commentaries[:3]:
                verse = kg.verses.get(commentary.verse_id)
                if verse:
                    st.markdown(f"• BG {verse.chapter}.{verse.verse} - {commentary.status}")

    elif node_type == 'author':
        st.markdown(f"**Author:** {node_key}")
        # Show works by this author
        author_commentaries = [c for c in kg.commentaries.values()
                             if c.original_author == node_key or c.substitute_author == node_key]
        st.markdown(f"**Total Works:** {len(author_commentaries)}")

        if author_commentaries:
            st.markdown("**Sample Works:**")
            for commentary in author_commentaries[:3]:
                verse = kg.verses.get(commentary.verse_id)
                if verse:
                    role = "Original" if commentary.original_author == node_key else "Substitute"
                    st.markdown(f"• BG {verse.chapter}.{verse.verse} ({commentary.school}) - {role}")

    else:
        st.markdown(f"**Node Type:** {node_type}")
        st.markdown(f"**ID:** {node_key}")
        st.markdown("*Node details not available*")

def export_graph_data(graph: nx.Graph, filename_prefix: str = "gita_graph"):
    """Export graph data in various formats"""
    if not graph.nodes():
        st.warning("No graph data to export")
        return
    
    # Prepare node data
    nodes_data = []
    for node_id, data in graph.nodes(data=True):
        node_info = {'id': node_id, **data}
        nodes_data.append(node_info)
    
    # Prepare edge data  
    edges_data = []
    for source, target, data in graph.edges(data=True):
        edge_info = {'source': source, 'target': target, **data}
        edges_data.append(edge_info)
    
    # Create downloadable files
    nodes_df = pd.DataFrame(nodes_data)
    edges_df = pd.DataFrame(edges_data)
    
    # CSV download
    nodes_csv = nodes_df.to_csv(index=False)
    edges_csv = edges_df.to_csv(index=False)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.download_button(
            "📥 Download Nodes CSV",
            nodes_csv,
            f"{filename_prefix}_nodes.csv",
            "text/csv"
        )
    
    with col2:
        st.download_button(
            "📥 Download Edges CSV", 
            edges_csv,
            f"{filename_prefix}_edges.csv",
            "text/csv"
        )
    
    # JSON download
    graph_json = {
        'nodes': nodes_data,
        'edges': edges_data,
        'metadata': {
            'total_nodes': len(nodes_data),
            'total_edges': len(edges_data),
            'export_timestamp': st.session_state.get('current_time', 'unknown')
        }
    }
    
    json_str = json.dumps(graph_json, indent=2, ensure_ascii=False)
    st.download_button(
        "📥 Download Full Graph JSON",
        json_str,
        f"{filename_prefix}_full.json",
        "application/json"
    )