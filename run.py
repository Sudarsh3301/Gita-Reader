#!/usr/bin/env python3
"""
Simple runner script for the Gita application
"""
import subprocess
import sys
import os

def main():
    """Run the Streamlit application"""
    try:
        # Check if we're in the right directory
        if not os.path.exists('skg.py'):
            print("❌ Error: skg.py not found in current directory")
            print("Please run this script from the gita-deployment directory")
            sys.exit(1)
        
        # Check if required files exist
        required_files = [
            'merged_gita_clean.json',
            'gita_faiss.index', 
            'gita_mappings.pkl'
        ]
        
        missing_files = [f for f in required_files if not os.path.exists(f)]
        if missing_files:
            print("❌ Error: Missing required files:")
            for f in missing_files:
                print(f"  - {f}")
            sys.exit(1)
        
        print("🚀 Starting Bhagavad Gita Semantic Search...")
        print("📂 All required files found")
        print("🌐 Application will be available at: http://localhost:8501")
        print("⏹️  Press Ctrl+C to stop the application")
        print("-" * 50)
        
        # Run streamlit
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", "skg.py",
            "--server.port=8501",
            "--server.address=localhost"
        ])
        
    except KeyboardInterrupt:
        print("\n👋 Application stopped by user")
    except Exception as e:
        print(f"❌ Error starting application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
