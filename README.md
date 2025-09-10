# Bhagavad Gita Semantic Search - Deployment Ready

## Overview
This is a deployment-ready version of the Bhagavad Gita Semantic Search application with per-verse AI commentary summaries.

## Features
- **Semantic Search**: Find relevant verses using natural language queries
- **Per-Verse AI Summaries**: Get combined AI summaries for each verse's commentaries
- **Interactive Knowledge Graph**: Visualize relationships between verses, concepts, and commentaries
- **Multiple Commentary Schools**: Access interpretations from various philosophical traditions
- **No Abstention Logic**: Always generates summaries when commentaries are available

## Files Included
- `skg.py` - Main Streamlit application
- `merged_gita_clean.json` - Complete Gita data with commentaries
- `gita_faiss.index` - Pre-built FAISS search index
- `gita_mappings.pkl` - Node mappings for the knowledge graph
- `requirements.txt` - Python dependencies
- `README.md` - This file

## Installation

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Application
```bash
streamlit run skg.py
```

The application will be available at `http://localhost:8501`

## Usage

### 1. Load the Index
- Click "📥 Load Prebuilt Index" in the sidebar
- Wait for the success message

### 2. Search
- Enter your philosophical question (e.g., "What is dharma?")
- Click "🔍 Search"

### 3. Generate AI Summaries
- Enable "Enable GROQ Summaries" in the sidebar
- Add your GROQ API key (or use the default)
- Click "Generate Combined Summaries for Each Verse"
- Each verse will get its own combined summary

### 4. Explore Results
- View Sanskrit text, translations, and word meanings
- Read individual commentaries from different schools
- See AI-generated combined summaries for each verse
- Use the Interactive Knowledge Graph (if enabled)

## Configuration

### GROQ API Key
The application includes a default GROQ API key, but you can provide your own:
1. Get a free API key from [Groq](https://console.groq.com/)
2. Enter it in the sidebar under "GROQ API Key"

### Search Settings
- **Number of results**: 1-20 verses
- **Interactive KG**: Enable for graph visualization
- **AI Enhancement**: Enable for commentary summaries

## Deployment Options

### Local Development
```bash
streamlit run skg.py
```

### Streamlit Cloud
1. Upload this directory to GitHub
2. Connect to Streamlit Cloud
3. Deploy directly

### Docker (Optional)
Create a `Dockerfile`:
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 8501
CMD ["streamlit", "run", "skg.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

## Key Changes from Original
- **Removed Abstention Logic**: Always generates summaries when commentaries exist
- **Per-Verse Summaries**: Each verse gets its own combined summary
- **No Light Mode**: Simplified interface
- **Better Error Handling**: Clear debug messages
- **Deployment Ready**: All files included and organized

## Troubleshooting

### "Index Not Found"
- Ensure all files are in the same directory
- Check that `gita_faiss.index` and `gita_mappings.pkl` exist

### "No Summaries Generated"
- Check your GROQ API key
- Ensure verses have commentaries
- Look at debug messages for specific errors

### "Import Errors"
- Run `pip install -r requirements.txt`
- Check Python version (3.8+ recommended)

## Support
For issues or questions, check the debug messages in the application interface.
