#!/usr/bin/env python3
"""
Test script to verify deployment readiness
"""
import os
import json
import pickle
import sys

def test_files():
    """Test if all required files are present and valid"""
    print("🔍 Testing deployment files...")
    print("=" * 50)
    
    # Required files
    files_to_check = {
        'skg.py': 'Main application file',
        'merged_gita_clean.json': 'Gita data file',
        'gita_faiss.index': 'FAISS search index',
        'gita_mappings.pkl': 'Node mappings',
        'requirements.txt': 'Python dependencies',
        'README.md': 'Documentation'
    }
    
    all_good = True
    
    for filename, description in files_to_check.items():
        if os.path.exists(filename):
            size = os.path.getsize(filename)
            print(f"✅ {filename} - {description} ({size:,} bytes)")
        else:
            print(f"❌ {filename} - {description} (MISSING)")
            all_good = False
    
    return all_good

def test_data_integrity():
    """Test if data files are valid"""
    print("\n🔍 Testing data integrity...")
    print("=" * 50)
    
    try:
        # Test JSON file
        with open('merged_gita_clean.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            if 'bhagavad_gita' in data:
                chapters = len(data['bhagavad_gita'])
                print(f"✅ JSON data valid - {chapters} chapters found")
            else:
                print("❌ JSON data invalid - missing 'bhagavad_gita' key")
                return False
    except Exception as e:
        print(f"❌ JSON data error: {e}")
        return False
    
    try:
        # Test pickle file
        with open('gita_mappings.pkl', 'rb') as f:
            mappings = pickle.load(f)
            if 'id_to_node' in mappings:
                nodes = len(mappings['id_to_node'])
                print(f"✅ Mappings valid - {nodes} nodes found")
            else:
                print("❌ Mappings invalid - missing 'id_to_node' key")
                return False
    except Exception as e:
        print(f"❌ Mappings error: {e}")
        return False
    
    return True

def test_imports():
    """Test if required packages can be imported"""
    print("\n🔍 Testing package imports...")
    print("=" * 50)
    
    packages = [
        ('streamlit', 'Streamlit web framework'),
        ('numpy', 'NumPy for numerical operations'),
        ('faiss', 'FAISS for similarity search'),
        ('sentence_transformers', 'Sentence transformers for embeddings'),
        ('requests', 'HTTP requests library'),
        ('json', 'JSON handling'),
        ('pickle', 'Pickle serialization'),
        ('datetime', 'Date/time utilities')
    ]
    
    all_imports_ok = True
    
    for package, description in packages:
        try:
            __import__(package)
            print(f"✅ {package} - {description}")
        except ImportError:
            print(f"❌ {package} - {description} (NOT INSTALLED)")
            all_imports_ok = False
    
    return all_imports_ok

def test_abstention_removal():
    """Test if abstention logic was properly removed"""
    print("\n🔍 Testing abstention logic removal...")
    print("=" * 50)
    
    try:
        with open('skg.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if abstention logic was removed
        if 'return False' in content and 'Always proceed - abstention logic removed' in content:
            print("✅ Abstention logic properly removed")
        else:
            print("❌ Abstention logic may not be properly removed")
            return False
        
        # Check if per-verse logic exists
        if 'Generate Combined Summaries for Each Verse' in content:
            print("✅ Per-verse summary logic present")
        else:
            print("❌ Per-verse summary logic missing")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking code: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Bhagavad Gita Deployment Test Suite")
    print("=" * 50)
    
    tests = [
        ("File Presence", test_files),
        ("Data Integrity", test_data_integrity),
        ("Package Imports", test_imports),
        ("Code Changes", test_abstention_removal)
    ]
    
    all_passed = True
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            if not result:
                all_passed = False
        except Exception as e:
            print(f"❌ {test_name} failed with error: {e}")
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 ALL TESTS PASSED - Deployment is ready!")
        print("\nTo run the application:")
        print("1. pip install -r requirements.txt")
        print("2. python run.py")
        print("   OR")
        print("2. streamlit run skg.py")
    else:
        print("❌ SOME TESTS FAILED - Please fix issues before deployment")
        sys.exit(1)

if __name__ == "__main__":
    main()
