import streamlit as st
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from collections import defaultdict, Counter
import re
from typing import Dict, List, Tuple, Any, Optional
import pickle
import os
from dataclasses import dataclass
import requests
from datetime import datetime
import hashlib
import uuid
import time

# Import the graph visualization module
try:
    from gita_graph_viz import (
        GitaGraphVisualizer,
        render_graph_visualization_panel,
        render_node_details_panel,
        export_graph_data
    )
    GRAPH_VIZ_AVAILABLE = True
except ImportError:
    GRAPH_VIZ_AVAILABLE = False

# Try to import pyvis for graph visualization
try:
    from pyvis.network import Network
    import networkx as nx
    PYVIS_AVAILABLE = True
    NETWORKX_AVAILABLE = True
except ImportError:
    PYVIS_AVAILABLE = False
    try:
        import networkx as nx
        NETWORKX_AVAILABLE = True
    except ImportError:
        NETWORKX_AVAILABLE = False
    # Don't show warning here - will show in UI when needed

# Configuration
EMBEDDING_MODEL = 'sentence-transformers/LaBSE'
FAISS_INDEX_PATH = "gita_faiss.index"
MAPPINGS_PATH = "gita_mappings.pkl"
DATA_FILE = "merged_gita_clean.json"
SUMMARIES_CACHE = "commentary_summaries.json"

# Free Trial Configuration
FREE_TRIAL_USES = 3
USAGE_TRACKING_FILE = "usage_tracking.json"

@dataclass
class VerseNode:
    id: str
    chapter: int
    verse: int
    shloka: str
    transliteration: str
    translations: Dict[str, str]
    word_meaning: Dict[str, str]

@dataclass
class ConceptNode:
    term: str
    meaning: str
    mentioned_in: List[str]

@dataclass
class CommentaryNode:
    id: str
    school: str
    status: str
    original_author: str
    substitute_author: str
    text: str
    verse_id: str

@dataclass
class SearchResult:
    verse: VerseNode
    score: float
    provenance_path: List[str]
    related_concepts: List[str]
    commentaries: List[CommentaryNode]
    support_count: int

# Usage Tracking Functions
def get_user_id():
    """Get or create a unique user ID for tracking usage"""
    if 'user_id' not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())
    return st.session_state.user_id

def load_usage_data():
    """Load usage tracking data from file"""
    try:
        if os.path.exists(USAGE_TRACKING_FILE):
            with open(USAGE_TRACKING_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_usage_data(usage_data):
    """Save usage tracking data to file"""
    try:
        with open(USAGE_TRACKING_FILE, 'w') as f:
            json.dump(usage_data, f, indent=2)
    except Exception:
        pass

def get_user_usage_count(user_id):
    """Get the current usage count for a user"""
    usage_data = load_usage_data()
    return usage_data.get(user_id, {}).get('usage_count', 0)

def increment_user_usage(user_id):
    """Increment usage count for a user"""
    usage_data = load_usage_data()
    if user_id not in usage_data:
        usage_data[user_id] = {
            'usage_count': 0,
            'first_use': datetime.now().isoformat(),
            'last_use': datetime.now().isoformat()
        }

    usage_data[user_id]['usage_count'] += 1
    usage_data[user_id]['last_use'] = datetime.now().isoformat()
    save_usage_data(usage_data)
    return usage_data[user_id]['usage_count']

def get_free_trial_api_key():
    """Get the free trial API key from secrets"""
    try:
        return st.secrets.get("groq_key", "")
    except Exception:
        return ""

def can_use_free_trial(user_id):
    """Check if user can still use free trial"""
    usage_count = get_user_usage_count(user_id)
    return usage_count < FREE_TRIAL_USES

def get_remaining_free_uses(user_id):
    """Get remaining free uses for a user"""
    usage_count = get_user_usage_count(user_id)
    return max(0, FREE_TRIAL_USES - usage_count)

def query_groq_with_usage_tracking(commentaries_data: List[Dict], query: str, api_key: str, is_free_trial: bool = False) -> Dict:
    """Wrapper for GROQ API that handles usage tracking for free trial"""
    if is_free_trial:
        user_id = get_user_id()
        if not can_use_free_trial(user_id):
            return {
                "summary": "INSUFFICIENT_GROUNDED_EVIDENCE",
                "direction": "insufficient_evidence",
                "supporting_ids": [],
                "supporting_schools": [],
                "confidence_score": 0.0,
                "note": "Free trial uses exhausted. Please add your own API key."
            }

        # Increment usage count for free trial
        new_count = increment_user_usage(user_id)
        remaining = FREE_TRIAL_USES - new_count

        # Call the actual API
        result = query_groq_api_aggregate(commentaries_data, query, api_key)

        # Add usage info to the result
        if isinstance(result, dict):
            result['free_trial_info'] = {
                'uses_remaining': remaining,
                'total_uses': FREE_TRIAL_USES
            }

        return result
    else:
        # Regular API call without usage tracking
        return query_groq_api_aggregate(commentaries_data, query, api_key)

# Cached resource loaders
@st.cache_resource
def load_faiss_index(path: str):
    """Load FAISS index with caching"""
    try:
        return faiss.read_index(path)
    except Exception as e:
        st.error(f"Failed to load FAISS index: {e}")
        return None

@st.cache_resource
def load_mappings(path: str):
    """Load mappings with caching"""
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        st.error(f"Failed to load mappings: {e}")
        return None

@st.cache_resource
def load_embedding_model(name: str = EMBEDDING_MODEL):
    """Load embedding model with caching"""
    try:
        model = SentenceTransformer('Lajavaness/bilingual-embedding-base', trust_remote_code=True)
        return model
    except Exception as e:
        st.error(f"Failed to load primary embedding model: {e}")
        try:
            model = SentenceTransformer('all-MiniLM-L6-v2')
            st.warning("Using fallback embedding model")
            return model
        except Exception as e2:
            st.error(f"Failed to load fallback embedding model: {e2}")
            return None

@st.cache_data
def load_knowledge_graph_data(data_file: str):
    """Load and process knowledge graph data with caching"""
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        st.error(f"Data file {data_file} not found.")
        return None

    verses = {}
    concepts = {}
    commentaries = {}
    schools = set()
    authors = set()
    
    # Store minimal metadata only
    verse_metadata = {}
    commentary_metadata = {}
    concept_metadata = {}

    gita_data = data.get('bhagavad_gita', [])
    if not gita_data:
        st.error("Invalid data format: 'bhagavad_gita' key not found")
        return None

    for chapter_data in gita_data:
        chapter_num = chapter_data.get('chapter')
        if not chapter_num:
            continue

        verses_data = chapter_data.get('verses', [])

        for verse_data in verses_data:
            verse_num = verse_data.get('verse')
            if not verse_num:
                continue

            verse_id = f"{chapter_num}:{verse_num}"

            # Store only essential verse data
            verse = VerseNode(
                id=verse_id,
                chapter=chapter_num,
                verse=verse_num,
                shloka=verse_data.get('shloka', ''),
                transliteration=verse_data.get('transliteration', ''),
                translations=verse_data.get('translations', {}),
                word_meaning=verse_data.get('word_meaning', {})
            )
            verses[verse_id] = verse
            
            # Store lightweight metadata
            verse_metadata[verse_id] = {
                'chapter': chapter_num,
                'verse': verse_num,
                'has_concepts': len(verse_data.get('word_meaning', {})) > 0,
                'has_commentaries': len(verse_data.get('commentaries', {})) > 0
            }

            # Process concepts
            for term, meaning in verse_data.get('word_meaning', {}).items():
                if term not in concepts:
                    concepts[term] = ConceptNode(
                        term=term,
                        meaning=meaning,
                        mentioned_in=[]
                    )
                concepts[term].mentioned_in.append(verse_id)

            # Process commentaries
            commentaries_data = verse_data.get('commentaries', {})
            for school, commentary_data in commentaries_data.items():
                if commentary_data.get('status') == 'missing' or not commentary_data.get('text'):
                    continue

                schools.add(school)
                commentary_id = f"{verse_id}_{school}"
                original_author = commentary_data.get('original_author', '')
                substitute_author = commentary_data.get('substitute_author', '')
                
                if original_author:
                    authors.add(original_author)
                if substitute_author:
                    authors.add(substitute_author)

                commentary = CommentaryNode(
                    id=commentary_id,
                    school=school,
                    status=commentary_data.get('status', 'original'),
                    original_author=original_author,
                    substitute_author=substitute_author,
                    text=commentary_data.get('text', ''),
                    verse_id=verse_id
                )
                commentaries[commentary_id] = commentary

    return {
        'verses': verses,
        'concepts': concepts,
        'commentaries': commentaries,
        'schools': schools,
        'authors': authors,
        'verse_metadata': verse_metadata,
        'commentary_metadata': commentary_metadata,
        'concept_metadata': concept_metadata
    }

@st.cache_resource  # Cache search results as in-memory resources to avoid pickling issues
def perform_search(query: str, top_k: int, _index, _mappings, _kg_data):
    """Perform cached search with TTL"""
    if not _index or not _mappings or not _kg_data:
        return []

    # Load model for encoding query
    model = load_embedding_model()
    if not model:
        return []

    # Encode query
    query_embedding = model.encode([query], normalize_embeddings=True)
    
    # Search FAISS index
    scores, indices = _index.search(query_embedding.astype('float32'), top_k * 3)
    
    # Process results
    candidate_verses = defaultdict(lambda: {
        'scores': [],
        'provenance_paths': [],
        'concepts': set(),
        'support_count': 0
    })
    
    id_to_node = _mappings['id_to_node']
    verses = _kg_data['verses']
    concepts = _kg_data['concepts']
    commentaries = _kg_data['commentaries']
    
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
            
        node_id = id_to_node[idx]
        node_type, node_key = node_id.split(':', 1)
        
        if node_type == 'verse':
            candidate_verses[node_key]['scores'].append(score)
            candidate_verses[node_key]['provenance_paths'].append(f"Query → Verse({node_key})")
            candidate_verses[node_key]['support_count'] += 1
            
        elif node_type == 'commentary':
            commentary = commentaries.get(node_key)
            if commentary:
                verse_id = commentary.verse_id
                candidate_verses[verse_id]['scores'].append(score * 0.9)
                candidate_verses[verse_id]['provenance_paths'].append(
                    f"Query → Commentary({commentary.school}) → Verse({verse_id})"
                )
                candidate_verses[verse_id]['support_count'] += 1
                
        elif node_type == 'concept':
            concept = concepts.get(node_key)
            if concept:
                for verse_id in concept.mentioned_in:
                    candidate_verses[verse_id]['scores'].append(score * 0.8)
                    candidate_verses[verse_id]['provenance_paths'].append(
                        f"Query → Concept({node_key}) → Verse({verse_id})"
                    )
                    candidate_verses[verse_id]['concepts'].add(node_key)
                    candidate_verses[verse_id]['support_count'] += 1

    # Create results
    results = []
    for verse_id, data in candidate_verses.items():
        verse = verses.get(verse_id)
        if not verse:
            continue
            
        avg_score = np.mean(data['scores']) if data['scores'] else 0
        concept_boost = len(data['concepts']) * 0.1
        support_boost = min(data['support_count'] * 0.05, 0.2)
        final_score = avg_score + concept_boost + support_boost
        
        # Get related commentaries
        verse_commentaries = [c for c in commentaries.values() if c.verse_id == verse_id]
        
        result = SearchResult(
            verse=verse,
            score=final_score,
            provenance_path=list(set(data['provenance_paths'])),
            related_concepts=list(data['concepts']),
            commentaries=verse_commentaries,
            support_count=data['support_count']
        )
        results.append(result)
    
    results.sort(key=lambda x: x.score, reverse=True)
    return results[:top_k]

def get_index_health_info():
    """Get health information about the current index"""
    health_info = {
        'index_exists': os.path.exists(FAISS_INDEX_PATH),
        'mappings_exist': os.path.exists(MAPPINGS_PATH),
        'data_exists': os.path.exists(DATA_FILE),
        'index_size': 0,
        'num_vectors': 0,
        'embedding_model': EMBEDDING_MODEL
    }
    
    if health_info['index_exists']:
        try:
            health_info['index_size'] = os.path.getsize(FAISS_INDEX_PATH) / (1024 * 1024)  # MB
            index = faiss.read_index(FAISS_INDEX_PATH)
            health_info['num_vectors'] = index.ntotal
        except:
            pass
    
    return health_info

def auto_load_index():
    """Automatically load index on first query"""
    if not st.session_state.get('index_ready', False):
        health = get_index_health_info()
        if health['index_exists'] and health['mappings_exist']:
            with st.spinner("Loading search index..."):
                index = load_faiss_index(FAISS_INDEX_PATH)
                mappings = load_mappings(MAPPINGS_PATH)
                kg_data = load_knowledge_graph_data(DATA_FILE)

                if index and mappings and kg_data:
                    st.session_state.index = index
                    st.session_state.mappings = mappings
                    st.session_state.kg_data = kg_data
                    st.session_state.index_ready = True
                    return True
    return st.session_state.get('index_ready', False)

def render_health_card():
    """Render system health card in sidebar"""
    st.sidebar.subheader("📊 System Status")

    if st.session_state.get('index_ready', False):
        st.sidebar.success("✅ Ready to Search")
        if st.session_state.get('kg_data'):
            kg_data = st.session_state.kg_data
            st.sidebar.write(f"📚 {len(kg_data['verses'])} verses")
            st.sidebar.write(f"🏫 {len(kg_data['schools'])} schools")
    else:
        st.sidebar.info("🔄 Will load on first search")

def render_custom_graph_visualization(subgraph: Dict, results: List[SearchResult], query: str):
    """Render a custom graph visualization that works with our data structure"""

    # Initialize session state for graph visualization
    if 'show_network_structure' not in st.session_state:
        st.session_state.show_network_structure = False
    if 'show_graph_stats' not in st.session_state:
        st.session_state.show_graph_stats = False
    if 'selected_graph_node' not in st.session_state:
        st.session_state.selected_graph_node = "Select a node..."

    st.subheader("🌐 Interactive Knowledge Graph")

    # Graph statistics in a nice layout
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📊 Nodes", len(subgraph['nodes']))
    with col2:
        st.metric("🔗 Edges", len(subgraph['edges']))
    with col3:
        st.metric("🔍 Results", len(results))
    with col4:
        # Calculate connectivity
        connectivity = len(subgraph['edges']) / max(len(subgraph['nodes']), 1)
        st.metric("🌐 Connectivity", f"{connectivity:.1f}")

    # Node type breakdown in an expander (always visible)
    with st.expander("📋 Node Type Breakdown", expanded=True):
        node_types = {}
        for node in subgraph['nodes']:
            node_type = node.split(':')[0]
            node_types[node_type] = node_types.get(node_type, 0) + 1

        # Create columns for node types
        if node_types:
            type_cols = st.columns(len(node_types))
            for i, (node_type, count) in enumerate(node_types.items()):
                with type_cols[i]:
                    st.metric(f"{node_type.title()}", count)

    # Interactive node explorer
    with st.expander("🔍 Node Explorer", expanded=True):
        # Node selection with session state
        selected_node = st.selectbox(
            "Select a node to explore:",
            ["Select a node..."] + subgraph['nodes'],
            key="node_selector",
            index=0 if st.session_state.selected_graph_node == "Select a node..." else
                  (subgraph['nodes'].index(st.session_state.selected_graph_node) + 1
                   if st.session_state.selected_graph_node in subgraph['nodes'] else 0)
        )

        if selected_node != "Select a node...":
            st.session_state.selected_graph_node = selected_node
            render_node_details(selected_node, subgraph, results)

    # Network structure visualization
    with st.expander("🕸️ Network Structure", expanded=st.session_state.show_network_structure):
        col_toggle, col_visual = st.columns([1, 3])

        with col_toggle:
            if st.button("🔄 Toggle Network View", key="toggle_network"):
                st.session_state.show_network_structure = not st.session_state.show_network_structure
                st.rerun()

        with col_visual:
            if st.session_state.show_network_structure:
                st.info("🌐 Network structure is displayed below")
            else:
                st.info("👆 Click toggle to show network structure")

        if st.session_state.show_network_structure:
            render_network_structure(subgraph)
            render_simple_graph_visualization(subgraph)

    # Graph statistics
    with st.expander("📊 Detailed Statistics", expanded=st.session_state.show_graph_stats):
        if st.button("📈 Toggle Statistics", key="toggle_stats"):
            st.session_state.show_graph_stats = not st.session_state.show_graph_stats
            st.rerun()

        if st.session_state.show_graph_stats:
            show_graph_statistics(subgraph, results)

    # Export functionality
    st.subheader("📥 Export Options")
    col1, col2 = st.columns(2)

    with col1:
        graph_export = {
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'subgraph': subgraph,
            'results_summary': [
                {
                    'verse_id': r.verse.id,
                    'score': r.score,
                    'concepts': r.related_concepts[:3],
                    'schools': [c.school for c in r.commentaries[:3]]
                } for r in results[:5]
            ]
        }

        st.download_button(
            label="📥 Download Graph JSON",
            data=json.dumps(graph_export, indent=2),
            file_name=f"gita_subgraph_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            key="download_graph"
        )

    with col2:
        # Create a simple text summary for download
        summary_text = f"""Knowledge Graph Summary
Query: {query}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Nodes: {len(subgraph['nodes'])}
Edges: {len(subgraph['edges'])}
Results: {len(results)}

Node Types:
"""
        for node_type, count in node_types.items():
            summary_text += f"- {node_type.title()}: {count}\n"

        st.download_button(
            label="📄 Download Summary",
            data=summary_text,
            file_name=f"gita_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            key="download_summary"
        )

def render_node_details(node_id: str, subgraph: Dict, results: List[SearchResult]):
    """Render details for a selected node"""

    st.markdown(f"### 📋 Node Details: `{node_id}`")

    node_type, node_key = node_id.split(':', 1)

    # Get node data
    node_data = subgraph.get('node_data', {}).get(node_id, {})

    if node_type == 'verse':
        st.markdown("**Type:** Verse")
        if node_data:
            st.write(f"**Chapter:** {node_data.get('chapter', 'N/A')}")
            st.write(f"**Verse:** {node_data.get('verse', 'N/A')}")
            st.write(f"**Score:** {node_data.get('score', 'N/A')}")

            if 'shloka' in node_data:
                st.markdown("**Sanskrit Text:**")
                st.code(node_data['shloka'])

        # Find related results
        for result in results:
            if result.verse.id == node_key:
                st.markdown("**English Translation:**")
                st.write(result.verse.translation)
                break

    elif node_type == 'concept':
        st.markdown("**Type:** Concept")
        st.write(f"**Term:** {node_key}")

        # Show which verses mention this concept
        related_verses = []
        for result in results:
            if node_key in result.related_concepts:
                related_verses.append(result.verse.id)

        if related_verses:
            st.markdown("**Mentioned in verses:**")
            for verse_id in related_verses[:5]:
                st.write(f"• {verse_id}")

    elif node_type == 'commentary':
        st.markdown("**Type:** Commentary")
        if node_data:
            st.write(f"**School:** {node_data.get('school', 'N/A')}")
            st.write(f"**Author:** {node_data.get('author', 'N/A')}")

            if 'text_preview' in node_data:
                st.markdown("**Text Preview:**")
                st.write(node_data['text_preview'])

    # Show connections
    connections = []
    for edge in subgraph['edges']:
        if edge['source'] == node_id:
            connections.append(f"→ {edge['target']} ({edge['relationship']})")
        elif edge['target'] == node_id:
            connections.append(f"← {edge['source']} ({edge['relationship']})")

    if connections:
        st.markdown("**Connections:**")
        for conn in connections[:10]:
            st.write(f"• {conn}")

def render_network_structure(subgraph: Dict):
    """Render a simple network structure visualization"""

    st.markdown("### 🕸️ Network Structure")

    # Group nodes by type
    nodes_by_type = {}
    for node in subgraph['nodes']:
        node_type = node.split(':', 1)[0]
        if node_type not in nodes_by_type:
            nodes_by_type[node_type] = []
        nodes_by_type[node_type].append(node)

    # Create a visual network representation
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("**Node Groups:**")

        # Show nodes in a more visual way
        for node_type, nodes in nodes_by_type.items():
            st.markdown(f"**{node_type.title()} ({len(nodes)} nodes):**")

            # Show first few nodes in columns
            if len(nodes) <= 6:
                node_cols = st.columns(min(len(nodes), 3))
                for i, node in enumerate(nodes):
                    with node_cols[i % 3]:
                        st.code(node.split(':', 1)[1][:20] + "..." if len(node.split(':', 1)[1]) > 20 else node.split(':', 1)[1])
            else:
                # Show first 6 and count the rest
                node_cols = st.columns(3)
                for i, node in enumerate(nodes[:6]):
                    with node_cols[i % 3]:
                        st.code(node.split(':', 1)[1][:20] + "..." if len(node.split(':', 1)[1]) > 20 else node.split(':', 1)[1])
                st.write(f"... and {len(nodes) - 6} more {node_type} nodes")

            st.markdown("---")

    with col2:
        st.markdown("**Connections:**")

        # Show edge relationships
        edge_types = {}
        for edge in subgraph['edges']:
            rel = edge['relationship']
            edge_types[rel] = edge_types.get(rel, 0) + 1

        for rel_type, count in edge_types.items():
            st.metric(rel_type.replace('_', ' ').title(), count)

        # Show some example connections
        st.markdown("**Example Connections:**")
        for i, edge in enumerate(subgraph['edges'][:5]):
            source_short = edge['source'].split(':', 1)[1][:15] + "..." if len(edge['source'].split(':', 1)[1]) > 15 else edge['source'].split(':', 1)[1]
            target_short = edge['target'].split(':', 1)[1][:15] + "..." if len(edge['target'].split(':', 1)[1]) > 15 else edge['target'].split(':', 1)[1]
            st.write(f"• {source_short} → {target_short}")

        if len(subgraph['edges']) > 5:
            st.write(f"... and {len(subgraph['edges']) - 5} more connections")

    # Network density and connectivity info
    st.markdown("### 📊 Network Metrics")

    total_nodes = len(subgraph['nodes'])
    total_edges = len(subgraph['edges'])
    max_possible_edges = total_nodes * (total_nodes - 1) // 2
    density = (total_edges / max_possible_edges) * 100 if max_possible_edges > 0 else 0

    metric_cols = st.columns(4)
    with metric_cols[0]:
        st.metric("Total Nodes", total_nodes)
    with metric_cols[1]:
        st.metric("Total Edges", total_edges)
    with metric_cols[2]:
        st.metric("Network Density", f"{density:.1f}%")
    with metric_cols[3]:
        avg_connections = (total_edges * 2) / total_nodes if total_nodes > 0 else 0
        st.metric("Avg Connections", f"{avg_connections:.1f}")

def render_simple_graph_visualization(subgraph: Dict):
    """Render a simple text-based graph visualization"""

    st.markdown("### 🎨 Visual Graph Representation")

    # Create a simple ASCII-style graph representation
    nodes_by_type = {}
    for node in subgraph['nodes']:
        node_type = node.split(':', 1)[0]
        if node_type not in nodes_by_type:
            nodes_by_type[node_type] = []
        nodes_by_type[node_type].append(node)

    # Create a visual representation
    graph_text = "```\n"
    graph_text += "Knowledge Graph Structure:\n"
    graph_text += "=" * 50 + "\n\n"

    # Show verses at the top
    if 'verse' in nodes_by_type:
        graph_text += "📜 VERSES:\n"
        for verse in nodes_by_type['verse'][:3]:  # Show first 3
            verse_id = verse.split(':', 1)[1]
            graph_text += f"   [{verse_id}]\n"

            # Show connections to this verse
            connections = []
            for edge in subgraph['edges']:
                if edge['target'] == verse:
                    source_id = edge['source'].split(':', 1)[1][:15]
                    connections.append(f"{source_id} --{edge['relationship']}--> ")
                elif edge['source'] == verse:
                    target_id = edge['target'].split(':', 1)[1][:15]
                    connections.append(f" --{edge['relationship']}--> {target_id}")

            for conn in connections[:2]:  # Show first 2 connections
                graph_text += f"     {conn}\n"

            if len(connections) > 2:
                graph_text += f"     ... and {len(connections) - 2} more connections\n"
            graph_text += "\n"

        if len(nodes_by_type['verse']) > 3:
            graph_text += f"   ... and {len(nodes_by_type['verse']) - 3} more verses\n\n"

    # Show concepts
    if 'concept' in nodes_by_type:
        graph_text += "💡 CONCEPTS:\n"
        concepts = [c.split(':', 1)[1] for c in nodes_by_type['concept'][:5]]
        graph_text += f"   {' <-> '.join(concepts)}\n\n"

        if len(nodes_by_type['concept']) > 5:
            graph_text += f"   ... and {len(nodes_by_type['concept']) - 5} more concepts\n\n"

    # Show commentaries
    if 'commentary' in nodes_by_type:
        graph_text += "📝 COMMENTARIES:\n"
        for commentary in nodes_by_type['commentary'][:3]:
            comm_id = commentary.split(':', 1)[1]
            graph_text += f"   ({comm_id})\n"

        if len(nodes_by_type['commentary']) > 3:
            graph_text += f"   ... and {len(nodes_by_type['commentary']) - 3} more commentaries\n"

    graph_text += "\n" + "=" * 50 + "\n"
    graph_text += f"Total: {len(subgraph['nodes'])} nodes, {len(subgraph['edges'])} connections\n"
    graph_text += "```"

    st.markdown(graph_text)

    # Interactive connection explorer
    st.markdown("### 🔗 Connection Explorer")

    # Show some interesting connection patterns
    connection_patterns = {}
    for edge in subgraph['edges']:
        source_type = edge['source'].split(':', 1)[0]
        target_type = edge['target'].split(':', 1)[0]
        relationship = edge['relationship']

        pattern = f"{source_type} --{relationship}--> {target_type}"
        connection_patterns[pattern] = connection_patterns.get(pattern, 0) + 1

    if connection_patterns:
        st.markdown("**Connection Patterns:**")
        for pattern, count in sorted(connection_patterns.items(), key=lambda x: x[1], reverse=True):
            st.write(f"• {pattern}: {count} connections")

    # Show a sample connection path
    if subgraph['edges']:
        st.markdown("**Sample Connection Path:**")
        sample_edge = subgraph['edges'][0]
        source_short = sample_edge['source'].split(':', 1)[1][:20]
        target_short = sample_edge['target'].split(':', 1)[1][:20]
        st.code(f"{source_short} --{sample_edge['relationship']}--> {target_short}")

        if len(subgraph['edges']) > 1:
            st.write(f"... and {len(subgraph['edges']) - 1} more connection paths")

def render_pyvis_graph_visualization(subgraph: Dict, results: List[SearchResult], query: str):
    """Render an interactive graph visualization using pyvis"""

    if not PYVIS_AVAILABLE:
        st.error("❌ Pyvis not available. Install with: pip install pyvis networkx")
        return

    st.subheader("🌐 Interactive Network Graph")

    # Create pyvis network
    net = Network(
        height="600px",
        width="100%",
        bgcolor="#222222",
        font_color="white",
        directed=True
    )

    # Configure physics
    net.set_options("""
    var options = {
      "physics": {
        "enabled": true,
        "stabilization": {"iterations": 100},
        "barnesHut": {
          "gravitationalConstant": -8000,
          "centralGravity": 0.3,
          "springLength": 95,
          "springConstant": 0.04,
          "damping": 0.09
        }
      }
    }
    """)

    # Color scheme for different node types
    node_colors = {
        'verse': '#FF6B6B',      # Red for verses
        'concept': '#4ECDC4',    # Teal for concepts
        'commentary': '#45B7D1', # Blue for commentaries
        'school': '#96CEB4',     # Green for schools
        'author': '#FFEAA7'      # Yellow for authors
    }

    # Add nodes with styling
    for node in subgraph['nodes']:
        node_type = node.split(':', 1)[0]
        node_id = node.split(':', 1)[1]

        # Get node data
        node_data = subgraph.get('node_data', {}).get(node, {})

        # Create label and title (hover text)
        if node_type == 'verse':
            label = f"Verse {node_id}"
            title = f"Verse {node_id}\nScore: {node_data.get('score', 'N/A')}\nChapter: {node_data.get('chapter', 'N/A')}"
            if 'shloka' in node_data:
                title += f"\n{node_data['shloka'][:50]}..."
            size = 25

        elif node_type == 'concept':
            label = node_id.title()
            title = f"Concept: {node_id}\nKey philosophical term"
            size = 20

        elif node_type == 'commentary':
            school = node_data.get('school', 'Unknown School')
            author = node_data.get('author', 'Unknown Author')
            label = f"{school[:15]}..."
            title = f"Commentary: {node_id}\nSchool: {school}\nAuthor: {author}"
            if 'text_preview' in node_data:
                title += f"\n{node_data['text_preview'][:100]}..."
            size = 15

        else:
            label = node_id
            title = f"{node_type.title()}: {node_id}"
            size = 12

        # Add node to network
        net.add_node(
            node,
            label=label,
            title=title,
            color=node_colors.get(node_type, '#95A5A6'),
            size=size,
            font={'size': 12, 'color': 'white'}
        )

    # Add edges with styling
    for edge in subgraph['edges']:
        source = edge['source']
        target = edge['target']
        relationship = edge['relationship']

        # Edge styling based on relationship type
        edge_colors = {
            'MENTIONS': '#FF6B6B',
            'COMMENTS_ON': '#4ECDC4',
            'RELATES_TO': '#45B7D1',
            'AUTHORED_BY': '#FFEAA7'
        }

        net.add_edge(
            source,
            target,
            label=relationship,
            color=edge_colors.get(relationship, '#95A5A6'),
            width=2,
            arrows={'to': {'enabled': True, 'scaleFactor': 1.2}}
        )

    # Generate and display the graph
    try:
        # Save the graph as HTML
        graph_html = net.generate_html()

        # Display in Streamlit
        st.components.v1.html(graph_html, height=650)

        # Graph controls and information
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("📊 Nodes", len(subgraph['nodes']))
        with col2:
            st.metric("🔗 Edges", len(subgraph['edges']))
        with col3:
            connectivity = len(subgraph['edges']) / max(len(subgraph['nodes']), 1)
            st.metric("🌐 Connectivity", f"{connectivity:.1f}")

        # Legend
        with st.expander("🎨 Graph Legend"):
            st.markdown("**Node Colors:**")
            col_leg1, col_leg2 = st.columns(2)

            with col_leg1:
                st.markdown("🔴 **Verses** - Sanskrit verses from the Gita")
                st.markdown("🔵 **Commentaries** - Scholarly interpretations")

            with col_leg2:
                st.markdown("🟢 **Concepts** - Philosophical terms")
                st.markdown("🟡 **Authors** - Commentary authors")

            st.markdown("**Interactions:**")
            st.markdown("- **Drag** nodes to rearrange")
            st.markdown("- **Hover** over nodes for details")
            st.markdown("- **Zoom** with mouse wheel")
            st.markdown("- **Pan** by dragging empty space")

        # Export options
        with st.expander("📥 Export Graph"):
            col_exp1, col_exp2 = st.columns(2)

            with col_exp1:
                if st.button("💾 Save Graph HTML"):
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"gita_graph_{timestamp}.html"

                    st.download_button(
                        label="📥 Download HTML",
                        data=graph_html,
                        file_name=filename,
                        mime="text/html"
                    )

            with col_exp2:
                # Export as NetworkX graph data
                if st.button("📊 Export NetworkX Data"):
                    nx_graph = create_networkx_graph(subgraph)
                    graph_data = {
                        'nodes': list(nx_graph.nodes(data=True)),
                        'edges': list(nx_graph.edges(data=True)),
                        'query': query,
                        'timestamp': datetime.now().isoformat()
                    }

                    st.download_button(
                        label="📥 Download NetworkX JSON",
                        data=json.dumps(graph_data, indent=2),
                        file_name=f"networkx_graph_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json"
                    )

    except Exception as e:
        st.error(f"❌ Error generating graph: {e}")
        st.info("Falling back to custom visualization...")
        render_custom_graph_visualization(subgraph, results, query)

def create_networkx_graph(subgraph: Dict):
    """Create a NetworkX graph from subgraph data"""

    if not NETWORKX_AVAILABLE:
        return None

    G = nx.DiGraph()

    # Add nodes with attributes
    for node in subgraph['nodes']:
        node_type = node.split(':', 1)[0]
        node_id = node.split(':', 1)[1]
        node_data = subgraph.get('node_data', {}).get(node, {})

        G.add_node(node,
                  type=node_type,
                  id=node_id,
                  **node_data)

    # Add edges with attributes
    for edge in subgraph['edges']:
        G.add_edge(edge['source'],
                  edge['target'],
                  relationship=edge['relationship'])

    return G

def show_graph_statistics(subgraph: Dict, results: List[SearchResult]):
    """Show detailed graph statistics"""

    st.markdown("### 📊 Graph Statistics")

    # Basic stats
    st.write(f"**Total Nodes:** {len(subgraph['nodes'])}")
    st.write(f"**Total Edges:** {len(subgraph['edges'])}")
    st.write(f"**Search Results:** {len(results)}")

    # Node type distribution
    node_types = {}
    for node in subgraph['nodes']:
        node_type = node.split(':', 1)[0]
        node_types[node_type] = node_types.get(node_type, 0) + 1

    st.markdown("**Node Distribution:**")
    for node_type, count in node_types.items():
        percentage = (count / len(subgraph['nodes'])) * 100
        st.write(f"• {node_type.title()}: {count} ({percentage:.1f}%)")

    # School distribution
    schools = set()
    for result in results:
        for commentary in result.commentaries:
            schools.add(commentary.school)

    st.write(f"**Schools Represented:** {len(schools)}")
    for school in sorted(schools):
        st.write(f"• {school}")

def create_subgraph_for_results(results: List[SearchResult], max_nodes: int = 50):
    """Create a focused subgraph for visualization"""
    if not GRAPH_VIZ_AVAILABLE:
        return None

    # Create a subgraph with relevant nodes and metadata
    nodes = []
    edges = []
    node_data = {}

    for result in results[:10]:  # Limit to top 10 results
        verse_id = f"verse:{result.verse.id}"

        # Add verse node with metadata
        if verse_id not in node_data:
            nodes.append(verse_id)
            node_data[verse_id] = {
                'type': 'verse',
                'id': result.verse.id,
                'chapter': result.verse.chapter,
                'verse': result.verse.verse,
                'shloka': result.verse.shloka[:100] + "..." if len(result.verse.shloka) > 100 else result.verse.shloka,
                'score': result.score
            }

        # Add concept nodes
        for concept in result.related_concepts[:3]:
            concept_id = f"concept:{concept}"
            if concept_id not in node_data:
                nodes.append(concept_id)
                node_data[concept_id] = {
                    'type': 'concept',
                    'term': concept,
                    'id': concept
                }
            edges.append({
                'source': verse_id,
                'target': concept_id,
                'relationship': "MENTIONS"
            })

        # Add commentary nodes
        for commentary in result.commentaries[:2]:
            commentary_id = f"commentary:{commentary.id}"
            if commentary_id not in node_data:
                nodes.append(commentary_id)
                node_data[commentary_id] = {
                    'type': 'commentary',
                    'id': commentary.id,
                    'school': commentary.school,
                    'author': commentary.original_author or commentary.substitute_author,
                    'text_preview': commentary.text[:200] + "..." if len(commentary.text) > 200 else commentary.text
                }
            edges.append({
                'source': commentary_id,
                'target': verse_id,
                'relationship': "COMMENTS_ON"
            })

    return {
        'nodes': nodes,
        'edges': edges,
        'node_data': node_data,
        'total_nodes': len(nodes),
        'total_edges': len(edges)
    }

def create_subgraph_for_results_fallback(results: List[SearchResult], max_nodes: int = 50):
    """Create a focused subgraph for visualization without external dependencies"""
    # Create a subgraph with relevant nodes and metadata
    nodes = []
    edges = []
    node_data = {}

    for result in results[:10]:  # Limit to top 10 results
        verse_id = f"verse:{result.verse.id}"

        # Add verse node with metadata
        if verse_id not in node_data:
            nodes.append(verse_id)
            node_data[verse_id] = {
                'type': 'verse',
                'id': result.verse.id,
                'chapter': result.verse.chapter,
                'verse': result.verse.verse,
                'shloka': result.verse.shloka[:100] + "..." if len(result.verse.shloka) > 100 else result.verse.shloka,
                'score': result.score
            }

        # Add concept nodes
        for concept in result.related_concepts[:3]:
            concept_id = f"concept:{concept}"
            if concept_id not in node_data:
                nodes.append(concept_id)
                node_data[concept_id] = {
                    'type': 'concept',
                    'term': concept,
                    'id': concept
                }
            edges.append({
                'source': verse_id,
                'target': concept_id,
                'relationship': "MENTIONS"
            })

        # Add commentary nodes
        for commentary in result.commentaries[:2]:
            commentary_id = f"commentary:{commentary.id}"
            if commentary_id not in node_data:
                nodes.append(commentary_id)
                node_data[commentary_id] = {
                    'type': 'commentary',
                    'id': commentary.id,
                    'school': commentary.school,
                    'author': commentary.original_author or commentary.substitute_author,
                    'text_preview': commentary.text[:200] + "..." if len(commentary.text) > 200 else commentary.text
                }
            edges.append({
                'source': commentary_id,
                'target': verse_id,
                'relationship': "COMMENTS_ON"
            })

    return {
        'nodes': nodes,
        'edges': edges,
        'node_data': node_data,
        'total_nodes': len(nodes),
        'total_edges': len(edges)
    }

def render_simple_node_list(subgraph: Dict):
    """Simple fallback visualization showing nodes and connections"""
    st.subheader("📊 Knowledge Graph Structure")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Nodes:**")
        node_types = {}
        for node in subgraph['nodes']:
            node_type = node.split(':', 1)[0]
            node_types[node_type] = node_types.get(node_type, 0) + 1
            st.write(f"• {node}")

    with col2:
        st.markdown("**Node Types:**")
        for node_type, count in node_types.items():
            st.metric(node_type.title(), count)

        st.markdown("**Connections:**")
        for edge in subgraph['edges'][:5]:
            source_short = edge['source'].split(':', 1)[1][:15]
            target_short = edge['target'].split(':', 1)[1][:15]
            st.write(f"• {source_short} → {target_short}")

        if len(subgraph['edges']) > 5:
            st.write(f"... and {len(subgraph['edges']) - 5} more connections")

def render_networkx_graph_visualization(subgraph: Dict, results: List[SearchResult], query: str):
    """Render graph using NetworkX (text-based layout)"""
    if not NETWORKX_AVAILABLE:
        st.error("NetworkX not available")
        return

    st.subheader("🌐 NetworkX Graph Analysis")

    # Create NetworkX graph
    G = create_networkx_graph(subgraph)
    if G is None:
        st.error("Failed to create NetworkX graph")
        return

    # Basic graph metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Nodes", G.number_of_nodes())
    with col2:
        st.metric("Edges", G.number_of_edges())
    with col3:
        density = nx.density(G)
        st.metric("Density", f"{density:.3f}")
    with col4:
        if G.number_of_nodes() > 0:
            avg_degree = sum(dict(G.degree()).values()) / G.number_of_nodes()
            st.metric("Avg Degree", f"{avg_degree:.1f}")

    # Show graph structure
    render_simple_node_list(subgraph)

def split_text_into_sentences(text: str, max_tokens: int = 200) -> List[str]:
    """Split text into sentences or short snippets with token limit"""
    if not text:
        return []

    # Simple sentence splitting on periods, exclamation marks, and question marks
    sentences = re.split(r'[.!?]+', text)
    snippets = []

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Rough token estimation (words * 1.3)
        estimated_tokens = len(sentence.split()) * 1.3

        if estimated_tokens <= max_tokens:
            snippets.append(sentence)
        else:
            # Split long sentences into chunks
            words = sentence.split()
            chunk_size = int(max_tokens / 1.3)
            for i in range(0, len(words), chunk_size):
                chunk = ' '.join(words[i:i + chunk_size])
                if chunk.strip():
                    snippets.append(chunk.strip())

    return snippets

def select_top_excerpts(commentaries_data: List[Dict], query: str, model,
                       max_excerpts: int = 16, max_per_school: int = 6) -> List[Dict]:
    """Select top excerpts using sentence-level similarity ranking with more lenient selection"""
    if not commentaries_data or not model:
        return []

    # Create excerpts with metadata - more lenient approach
    excerpts = []
    school_counts = defaultdict(int)

    for commentary in commentaries_data:
        school = commentary['school']
        text = commentary['text']
        commentary_id = commentary['id']

        # More generous per-school limit
        if school_counts[school] >= max_per_school:
            continue

        # Split into sentences/snippets
        sentences = split_text_into_sentences(text)

        for sentence in sentences:
            if len(sentence.strip()) < 5:  # More lenient minimum length
                continue

            excerpts.append({
                'id': commentary_id,
                'school': school,
                'text': sentence,
                'original_commentary': commentary
            })
            school_counts[school] += 1

            # More generous stopping condition
            if school_counts[school] >= max_per_school:
                break

    # If no excerpts found, fallback to using full commentaries
    if not excerpts:
        for commentary in commentaries_data:
            if len(commentary['text'].strip()) > 5:
                excerpts.append({
                    'id': commentary['id'],
                    'school': commentary['school'],
                    'text': commentary['text'][:500],  # Use first 500 chars
                    'original_commentary': commentary
                })

    if not excerpts:
        return []

    # Compute similarities with fallback
    try:
        query_embedding = model.encode([query], normalize_embeddings=True)
        excerpt_texts = [excerpt['text'] for excerpt in excerpts]
        excerpt_embeddings = model.encode(excerpt_texts, normalize_embeddings=True)

        # Calculate cosine similarities
        similarities = np.dot(excerpt_embeddings, query_embedding.T).flatten()

        # Add similarity scores to excerpts
        for i, excerpt in enumerate(excerpts):
            excerpt['similarity'] = float(similarities[i])

        # Sort by similarity and take top N - more lenient threshold
        excerpts.sort(key=lambda x: x['similarity'], reverse=True)

        # Take top excerpts but ensure we have at least some content
        selected = excerpts[:max_excerpts]

        # If similarity scores are very low, still return some excerpts
        if not selected or (selected and selected[0]['similarity'] < 0.1):
            # Return top excerpts regardless of similarity score
            return excerpts[:min(8, len(excerpts))]

        return selected

    except Exception as e:
        # Fallback: return excerpts without similarity ranking
        return excerpts[:min(max_excerpts, len(excerpts))]

def compute_hybrid_confidence(supporting_excerpts: List[Dict], total_schools: int,
                             support_count: int, N: int = 8, model_confidence: float = None) -> float:
    """Compute hybrid confidence score based on coverage and support strength"""
    if not supporting_excerpts:
        return 0.0

    # Coverage (distinct schools)
    distinct_schools = len(set(excerpt['school'] for excerpt in supporting_excerpts))
    coverage = distinct_schools / min(total_schools, 4)

    # Support strength
    support_strength = support_count / N

    # Computed confidence (without similarity component)
    computed_confidence = 0.2 * coverage + 0.1 * support_strength

    # If model provided confidence, average with computed value
    if model_confidence is not None and isinstance(model_confidence, (int, float)):
        final_confidence = 0.5 * model_confidence + 0.5 * computed_confidence
    else:
        # Use computed confidence as default
        final_confidence = computed_confidence

    return min(final_confidence, 1.0)

def should_abstain(supporting_excerpts: List[Dict], support_count: int, N: int = 8) -> bool:
    """Always proceed - abstention logic removed"""
    return False

def query_groq_api_aggregate(commentaries_data: List[Dict], query: str, api_key: str) -> Dict:
    """
    Aggregate commentary analysis with single grounded synthesis

    Args:
        commentaries_data: [{ "id": "C1", "school": "Sri Vaisnava Sampradaya", "text": "..." }, ...]
        query: user question
        api_key: GROQ API key
    Returns:
        JSON dict with keys: summary, direction, supporting_ids, supporting_schools, confidence_score, note
    """
    if not api_key or not commentaries_data:
        return {
            "summary": "INSUFFICIENT_GROUNDED_EVIDENCE",
            "direction": "insufficient_evidence",
            "supporting_ids": [],
            "supporting_schools": [],
            "confidence_score": 0.0,
            "note": "No commentaries provided or API key missing."
        }

    # Load embedding model for excerpt selection
    model = load_embedding_model()
    if not model:
        return {
            "summary": "INSUFFICIENT_GROUNDED_EVIDENCE",
            "direction": "insufficient_evidence",
            "supporting_ids": [],
            "supporting_schools": [],
            "confidence_score": 0.0,
            "note": "Failed to load embedding model for excerpt selection."
        }

    # Step 1: Pre-call excerpt selection
    selected_excerpts = select_top_excerpts(commentaries_data, query, model)

    if not selected_excerpts:
        return {
            "summary": "INSUFFICIENT_GROUNDED_EVIDENCE",
            "direction": "insufficient_evidence",
            "supporting_ids": [],
            "supporting_schools": [],
            "confidence_score": 0.0,
            "note": f"No relevant excerpts found after selection from {len(commentaries_data)} commentaries."
        }

    # Step 2: No abstention - proceed with all selected excerpts
    support_count = len(selected_excerpts)

    # Step 3: Construct prompt
    try:
        # Build excerpt bundle
        excerpt_bundle = f'User question: "{query}"\nEXCERPTS:\n'
        for excerpt in selected_excerpts:
            excerpt_bundle += f"{excerpt['id']} | {excerpt['school']} | \"{excerpt['text'][:200]}...\"\n"

        # Few-shot example
        example = '''Example:
User question: "What is dharma?"
EXCERPTS:
C1 | Sri Vaisnava Sampradaya | "Dharma means righteous duty according to one's station in life..."
C2 | Advaita Vedanta | "Dharma is the eternal law that upholds cosmic order..."

Expected JSON:
{
  "summary": "Dharma represents righteous duty and eternal law that maintains cosmic order according to one's life circumstances.",
  "direction": "practical_action",
  "supporting_ids": ["C1", "C2"],
  "supporting_schools": ["Sri Vaisnava Sampradaya", "Advaita Vedanta"],
  "confidence_score": 0.8,
  "note": "Strong consensus across schools on dharma as duty and cosmic law."
}'''

        instruction = '''Instruction: You must respond with ONLY valid JSON. No other text. Produce JSON with these exact keys: summary (2-3 sentence synthesis to answer the user question), direction (practical_action|renunciation|devotional|mixed), supporting_ids (array of excerpt IDs used), supporting_schools (array of schools), confidence_score (0.0-1.0), note (short justification). Example format:
{"summary": "Your synthesis here", "direction": "mixed", "supporting_ids": ["C1"], "supporting_schools": ["School Name"], "confidence_score": 0.8, "note": "Justification"}'''

        full_prompt = f"{example}\n\n{excerpt_bundle}\n{instruction}"

        # Check context length (rough estimation)
        estimated_tokens = len(full_prompt.split()) * 1.3
        if estimated_tokens > 2800:  # Leave margin for response
            # Truncate excerpts if too long
            selected_excerpts = selected_excerpts[:6]
            excerpt_bundle = f'User question: "{query}"\nEXCERPTS:\n'
            for excerpt in selected_excerpts:
                excerpt_bundle += f"{excerpt['id']} | {excerpt['school']} | \"{excerpt['text'][:150]}...\"\n"
            full_prompt = f"{example}\n\n{excerpt_bundle}\n{instruction}"

        # Step 4: Model call
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': 'llama-3.1-8b-instant',
            'messages': [
                {
                    'role': 'system',
                    'content': 'You are a scholar of Hindu exegesis. Use only provided excerpts. Do not add facts or invent attributions. You must respond with ONLY valid JSON - no explanations, no markdown, no extra text. Just pure JSON.'
                },
                {
                    'role': 'user',
                    'content': full_prompt
                }
            ],
            'max_tokens': 400,
            'temperature': 0.0  # Deterministic
        }

        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=15
        )

        if response.status_code != 200:
            error_note = f"API error: {response.status_code}"
            if response.status_code == 401:
                error_note += " - Invalid API key"
            elif response.status_code == 429:
                error_note += " - Rate limit exceeded"
            elif response.status_code == 500:
                error_note += " - Server error"

            return {
                "summary": "INSUFFICIENT_GROUNDED_EVIDENCE",
                "direction": "insufficient_evidence",
                "supporting_ids": [],
                "supporting_schools": [],
                "confidence_score": 0.0,
                "note": error_note
            }

        raw_content = response.json()['choices'][0]['message']['content'].strip()

        # Step 5: JSON schema enforcement with better parsing
        def extract_json_from_text(text):
            """Extract JSON from text that might contain extra content"""
            # Try to find JSON block
            import re

            # Look for JSON block between curly braces
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json_match.group(0)

            # If no JSON found, return original text
            return text

        try:
            # First try direct parsing
            result = json.loads(raw_content)
        except json.JSONDecodeError:
            try:
                # Try extracting JSON from the response
                extracted_json = extract_json_from_text(raw_content)
                result = json.loads(extracted_json)
            except json.JSONDecodeError:
                # Create a fallback response based on the excerpts
                fallback_summary = f"Based on {len(selected_excerpts)} commentary excerpts, this verse addresses the question about {query.lower()}."

                return {
                    "summary": fallback_summary,
                    "direction": "mixed",
                    "supporting_ids": [excerpt['id'] for excerpt in selected_excerpts[:3]],
                    "supporting_schools": list(set(excerpt['school'] for excerpt in selected_excerpts[:3])),
                    "confidence_score": 0.6,
                    "note": f"Fallback response - model output was not valid JSON. Raw: {raw_content[:100]}..."
                }

        # Step 6: Post-validate fields
        allowed_directions = {"practical_action", "renunciation", "devotional", "jnana", "mixed", "insufficient_evidence"}
        provided_ids = set(excerpt['id'] for excerpt in selected_excerpts)

        # Validate and fix fields
        if 'direction' not in result or result['direction'] not in allowed_directions:
            result['direction'] = 'mixed'

        if 'supporting_ids' not in result or not isinstance(result['supporting_ids'], list):
            result['supporting_ids'] = []
        else:
            # Filter to only provided IDs
            result['supporting_ids'] = [id for id in result['supporting_ids'] if id in provided_ids]

        if 'supporting_schools' not in result or not isinstance(result['supporting_schools'], list):
            result['supporting_schools'] = []
        else:
            # Validate schools match the supporting IDs
            valid_schools = set()
            for excerpt in selected_excerpts:
                if excerpt['id'] in result['supporting_ids']:
                    valid_schools.add(excerpt['school'])
            result['supporting_schools'] = list(valid_schools)

        if 'confidence_score' not in result or not isinstance(result['confidence_score'], (int, float)):
            result['confidence_score'] = 0.0
        else:
            result['confidence_score'] = max(0.0, min(1.0, float(result['confidence_score'])))

        if 'summary' not in result:
            result['summary'] = "INSUFFICIENT_GROUNDED_EVIDENCE"

        if 'note' not in result:
            result['note'] = "N/A"

        # Step 7: Compute hybrid confidence (average with model confidence if provided)
        total_schools = len(set(commentary['school'] for commentary in commentaries_data))
        supporting_excerpts = [e for e in selected_excerpts if e['id'] in result['supporting_ids']]
        model_confidence = result.get('confidence_score', None)

        hybrid_confidence = compute_hybrid_confidence(
            supporting_excerpts,
            total_schools,
            len(supporting_excerpts),
            N=len(selected_excerpts),
            model_confidence=model_confidence
        )
        result['confidence_score'] = hybrid_confidence

        # Step 8: No abstention check - always proceed with result

        # Step 9: Logging (basic)
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "selected_excerpt_count": len(selected_excerpts),
            "selected_excerpt_ids": [e['id'] for e in selected_excerpts],
            "supporting_excerpt_count": len(supporting_excerpts),
            "total_schools": total_schools,
            "model_confidence": model_confidence,
            "hybrid_confidence": hybrid_confidence,
            "raw_model_output": raw_content,
            "final_result": result
        }

        # Save to log file (append mode)
        try:
            with open("groq_aggregate_logs.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            # Don't fail the main function if logging fails
            pass

        return result

    except Exception as e:
        return {
            "summary": "INSUFFICIENT_GROUNDED_EVIDENCE",
            "direction": "insufficient_evidence",
            "supporting_ids": [],
            "supporting_schools": [],
            "confidence_score": 0.0,
            "note": f"Error during processing: {str(e)}"
        }



def render_search_result_minimal(result: SearchResult, result_num: int, enable_groq: bool = False, groq_api_key: str = ""):
    """Render search result in minimal format with optional AI summary generation"""
    verse = result.verse

    st.markdown(f"### {result_num}. Chapter {verse.chapter}, Verse {verse.verse}")

    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown(f"**Score:** {result.score:.3f}")
    with col2:
        if result.support_count > 1:
            st.success(f"Consensus ({result.support_count})")

    # Sanskrit and translations
    st.markdown(f"**Sanskrit:** {verse.shloka}")

    # Show both Hindi and English translations prominently
    if 'hindi' in verse.translations:
        st.markdown(f"**Hindi:** {verse.translations['hindi']}")

    if 'english' in verse.translations:
        st.markdown(f"**English:** {verse.translations['english']}")

    # Individual AI Summary Generation Button
    if enable_groq and groq_api_key and result.commentaries:
        col_summary1, col_summary2 = st.columns([3, 1])
        with col_summary1:
            st.markdown("**🤖 AI Commentary Analysis**")
        with col_summary2:
            if st.button(f"Generate Summary", key=f"generate_summary_{verse.id}_{result_num}"):
                try:
                    with st.spinner(f"Generating AI summary for verse {verse.id}..."):
                        # Collect commentaries for this specific verse
                        verse_commentaries = []
                        for i, commentary in enumerate(result.commentaries):
                            if commentary.text and len(commentary.text.strip()) > 10:
                                verse_commentaries.append({
                                    'id': f"C{i+1}",
                                    'school': commentary.school,
                                    'text': commentary.text
                                })

                        if verse_commentaries:
                            # Generate summary for this specific verse
                            is_free_trial = st.session_state.get('using_free_trial', False)
                            verse_summary = query_groq_with_usage_tracking(
                                verse_commentaries,
                                st.session_state.get('last_query', ''),
                                groq_api_key,
                                is_free_trial
                            )

                            # Store in session state
                            if 'verse_summaries' not in st.session_state:
                                st.session_state.verse_summaries = {}
                            st.session_state.verse_summaries[verse.id] = verse_summary

                            # Show success/failure message
                            if verse_summary.get('summary') != "INSUFFICIENT_GROUNDED_EVIDENCE":
                                st.success(f"✅ Summary generated for verse {verse.id}")

                                # Show free trial usage info if applicable
                                if is_free_trial:
                                    user_id = get_user_id()
                                    remaining = get_remaining_free_uses(user_id)
                                    if remaining > 0:
                                        st.info(f"🎁 Free trial: {remaining} uses remaining")
                                    else:
                                        st.warning("🚫 Free trial exhausted. Add your own API key to continue.")
                            else:
                                st.warning(f"Could not generate reliable summary for verse {verse.id}")

                            st.rerun()
                        else:
                            st.error("No valid commentaries found for this verse")
                except Exception as e:
                    st.error(f"Error generating summary: {str(e)}")
                    # Don't rerun on error to avoid infinite loops

    # Display per-verse AI summary if available
    verse_summaries = st.session_state.get('verse_summaries', {})
    if verse.id in verse_summaries:
        verse_summary = verse_summaries[verse.id]
        if verse_summary.get('summary') != "INSUFFICIENT_GROUNDED_EVIDENCE":
            with st.expander("🤖 AI Commentary Summary", expanded=True):
                st.markdown(f"**Summary:** {verse_summary.get('summary', 'N/A')}")

                direction = verse_summary.get('direction', 'N/A')
                if direction != 'N/A':
                    st.markdown(f"**Direction:** {direction.replace('_', ' ').title()}")

                confidence = verse_summary.get('confidence_score', 0)
                if confidence > 0:
                    # Color-coded confidence display
                    if confidence >= 0.7:
                        st.success(f"**Confidence:** {confidence:.2f} (High)")
                    elif confidence >= 0.4:
                        st.warning(f"**Confidence:** {confidence:.2f} (Medium)")
                    else:
                        st.error(f"**Confidence:** {confidence:.2f} (Low)")

                supporting_schools = verse_summary.get('supporting_schools', [])
                if supporting_schools:
                    st.markdown(f"**Supporting Schools:** {', '.join(supporting_schools)}")

                note = verse_summary.get('note', '')
                if note and note != 'N/A':
                    st.markdown(f"**Note:** {note}")
            st.markdown("---")
    
    # Expandable sections
    with st.expander("📖 Word Meanings & Details"):
        if verse.transliteration:
            st.markdown(f"**Transliteration:** {verse.transliteration}")

        if verse.word_meaning:
            st.markdown("**Word Meanings:**")
            # Create compact horizontal layout for word meanings
            meanings_text = " | ".join([f"**{term}:** {meaning}" for term, meaning in verse.word_meaning.items()])
            st.markdown(meanings_text)
    
    if result.related_concepts:
        st.markdown(f"**Related Concepts:** {', '.join(result.related_concepts)}")
    
    # Commentaries with lazy loading
    if result.commentaries:
        with st.expander(f"📚 Commentaries ({len(result.commentaries)})"):
            for commentary in result.commentaries:
                st.markdown(f"**{commentary.school}** ({commentary.status})")

                if commentary.original_author:
                    st.markdown(f"*Author:* {commentary.original_author}")

                # Full text toggle
                show_key = f"show_full_{verse.id}_{commentary.school}_{result_num}"
                if show_key not in st.session_state:
                    st.session_state[show_key] = False

                if st.button(f"{'Hide' if st.session_state[show_key] else 'Show'} Full Text",
                           key=f"btn_{show_key}"):
                    st.session_state[show_key] = not st.session_state[show_key]

                if st.session_state[show_key]:
                    st.markdown(commentary.text)

                st.markdown("---")

def main():
    st.set_page_config(
        page_title="Sacred Semantics",
        page_icon="🕉️",
        layout="wide"
    )
    



    
    # Initialize session state with minimal data
    if 'search_performed' not in st.session_state:
        st.session_state.search_performed = False
    if 'current_results' not in st.session_state:
        st.session_state.current_results = []
    if 'verse_summaries' not in st.session_state:
        st.session_state.verse_summaries = {}
    if 'kg_built' not in st.session_state:
        st.session_state.kg_built = False
    if 'index_ready' not in st.session_state:
        st.session_state.index_ready = False


    
    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Health card
        render_health_card()
        st.markdown("---")


        
        # Search configuration
        max_results = 20
        
        # Search configuration form
        with st.form("search_config"):
            num_results = st.slider("Number of results", 1, max_results, 3)

            # GROQ settings (basic configuration only)
            st.subheader("🤖 AI Enhancement")
            enable_groq = st.checkbox("Enable GROQ Summaries", value=False)

            # Interactive KG
            if GRAPH_VIZ_AVAILABLE or PYVIS_AVAILABLE:
                enable_kg = st.checkbox("Enable Interactive KG", value=False)
                if enable_kg and not PYVIS_AVAILABLE and not NETWORKX_AVAILABLE:
                    st.warning("⚠️ Graph visualization libraries not available. Will use text-based visualization.")
            else:
                enable_kg = st.checkbox("Enable Basic KG (Text-based)", value=False)
                if enable_kg:
                    st.info("💡 For interactive graphs, install: pip install pyvis networkx")

            st.form_submit_button("Update Settings")

        # Free trial and API key configuration (outside form)
        groq_api_key = ""
        using_free_trial = False

        if enable_groq:
            st.subheader("🔑 API Key Configuration")
            user_id = get_user_id()
            remaining_uses = get_remaining_free_uses(user_id)

            # Show free trial status and button
            if remaining_uses > 0:
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.success(f"🎁 Free Trial: {remaining_uses} uses remaining")
                with col2:
                    if st.button("Use Free Trial", key="use_free_trial"):
                        free_trial_key = get_free_trial_api_key()
                        if free_trial_key:
                            st.session_state.groq_api_key = free_trial_key
                            st.session_state.using_free_trial = True
                            st.success("✅ Free trial activated!")
                            st.rerun()
                        else:
                            st.error("Free trial API key not configured on server")
            else:
                st.warning("🚫 Free trial uses exhausted")

            # Check if free trial is active
            if st.session_state.get('using_free_trial', False) and st.session_state.get('groq_api_key'):
                groq_api_key = st.session_state.groq_api_key
                using_free_trial = True
                st.info("🎁 Using free trial API key")

            # Option to use own API key
            st.markdown("**Or use your own API key:**")
            groq_api_key_input = st.text_input("GROQ API Key", type="password",
                                             help="Get a free API key from https://console.groq.com/")
            if groq_api_key_input:
                groq_api_key = groq_api_key_input
                using_free_trial = False
                st.session_state.using_free_trial = False
                st.session_state.groq_api_key = groq_api_key_input

            if not groq_api_key:
                if remaining_uses > 0:
                    st.info("💡 Click 'Use Free Trial' above or add your own GROQ API key.")
                else:
                    st.info("💡 Add your GROQ API key to continue using AI summaries.")
        

        
        # Example queries
        st.subheader("💡 Example Queries")
        example_queries = [
            "What is dharma?",
            "How to achieve moksha?",
            "Nature of the self",
            "Karma yoga principles"
        ]
        
        for query in example_queries:
            if st.button(query, key=f"ex_{query}", use_container_width=True):
                st.session_state.example_query = query
    
    # Main content area
    st.title("Sacred Semantics")
    st.markdown("*From shloka to insight, instantly*.Discover meanings, perspectives, and schools of thought woven into the Bhagavad Gita — powered by knowledge graphs and semantic search")
    
    # Search interface
    st.header("🔍 Search Interface")
    
    # Search input
    search_query = st.text_input(
        "Enter your philosophical question:",
        value=st.session_state.get('example_query', ''),
        placeholder="e.g., What is the nature of dharma?",
        help="Ask questions about Hindu philosophy, spiritual concepts, or specific teachings"
    )
    
    # Search button
    if st.button("🔍 Search", type="primary", disabled=not search_query):
        # Auto-load index if not ready
        if not auto_load_index():
            st.error("❌ Failed to load search index. Please check if all required files are present.")
            return

        with st.spinner("Searching..."):
            # Perform cached search
            results = perform_search(
                search_query,
                num_results,
                st.session_state.index,
                st.session_state.mappings,
                st.session_state.kg_data
            )

            st.session_state.current_results = results
            st.session_state.search_performed = True
            st.session_state.last_query = search_query

            if results:
                st.success(f"Found {len(results)} relevant results")
            else:
                st.warning("No results found. Try a different query.")
    
    # Display results
    if st.session_state.search_performed and st.session_state.current_results:
        results = st.session_state.current_results
        
        # Individual AI summaries are now generated per-verse using buttons in each result
        if enable_groq and groq_api_key and results:
            st.info("💡 **Per-Verse AI Summaries**: Use the 'Generate Summary' button on each verse result below to get focused AI commentary analysis.")


        # Results display
        if enable_kg:
            # Tabbed interface for full mode
            tab1, tab2 = st.tabs(["📖 Search Results", "🌐 Knowledge Graph"])

            with tab1:
                st.subheader("Search Results")
                for i, result in enumerate(results, 1):
                    render_search_result_minimal(result, i, enable_groq, groq_api_key)
                    st.markdown("---")

            with tab2:
                st.subheader("🌐 Knowledge Graph Visualization")

                # Check available visualization options
                if PYVIS_AVAILABLE:
                    viz_option = st.radio("Visualization Type:",
                                        ["Interactive Graph (Pyvis)", "Text-based Graph"],
                                        index=0)
                elif NETWORKX_AVAILABLE:
                    viz_option = st.radio("Visualization Type:",
                                        ["NetworkX Analysis", "Text-based Graph"],
                                        index=0)
                else:
                    viz_option = "Text-based Graph"
                    st.info("💡 Install pyvis and networkx for interactive graphs: `pip install pyvis networkx`")

                if st.button("🔍 Build Knowledge Graph"):
                    with st.spinner("Building knowledge graph..."):
                        # Create subgraph regardless of visualization libraries
                        subgraph = create_subgraph_for_results_fallback(results)
                        if subgraph:
                            st.success(f"Built subgraph with {len(subgraph['nodes'])} nodes and {len(subgraph['edges'])} connections")

                            # Choose visualization based on available libraries
                            try:
                                if viz_option == "Interactive Graph (Pyvis)" and PYVIS_AVAILABLE:
                                    render_pyvis_graph_visualization(subgraph, results, st.session_state.last_query)
                                elif viz_option == "NetworkX Analysis" and NETWORKX_AVAILABLE:
                                    render_networkx_graph_visualization(subgraph, results, st.session_state.last_query)
                                else:
                                    # Text-based fallback
                                    render_custom_graph_visualization(subgraph, results, st.session_state.last_query)

                            except Exception as e:
                                st.error(f"Graph visualization error: {e}")
                                st.info("Falling back to text-based visualization")
                                try:
                                    render_custom_graph_visualization(subgraph, results, st.session_state.last_query)
                                except Exception as e2:
                                    st.error(f"Fallback visualization error: {e2}")
                                    # Final fallback: Show simple node list
                                    render_simple_node_list(subgraph)
                        else:
                            st.warning("Failed to create subgraph - no valid data found")
        else:
            # Simple results display
            st.subheader("📖 Search Results")
            for i, result in enumerate(results, 1):
                render_search_result_minimal(result, i, enable_groq, groq_api_key)
                if i < len(results):
                    st.markdown("---")


    
    # Statistics (collapsed by default)
    if st.session_state.get('kg_data'):
        with st.expander("📊 Knowledge Graph Statistics"):
            kg_data = st.session_state.kg_data
            
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Verses", len(kg_data['verses']))
            with col2:
                st.metric("Concepts", len(kg_data['concepts']))
            with col3:
                st.metric("Commentaries", len(kg_data['commentaries']))
            with col4:
                st.metric("Schools", len(kg_data['schools']))
            with col5:
                st.metric("Authors", len(kg_data['authors']))

if __name__ == "__main__":
    main()