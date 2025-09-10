#!/usr/bin/env python3
"""
Test script for the free trial functionality
"""

import json
import os
import uuid
from datetime import datetime

# Configuration
FREE_TRIAL_USES = 3
USAGE_TRACKING_FILE = "usage_tracking.json"

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

def can_use_free_trial(user_id):
    """Check if user can still use free trial"""
    usage_count = get_user_usage_count(user_id)
    return usage_count < FREE_TRIAL_USES

def get_remaining_free_uses(user_id):
    """Get remaining free uses for a user"""
    usage_count = get_user_usage_count(user_id)
    return max(0, FREE_TRIAL_USES - usage_count)

def test_free_trial_system():
    """Test the free trial system"""
    print("Testing Free Trial System")
    print("=" * 40)
    
    # Create a test user
    test_user_id = str(uuid.uuid4())
    print(f"Test User ID: {test_user_id}")
    
    # Test initial state
    print(f"Initial usage count: {get_user_usage_count(test_user_id)}")
    print(f"Can use free trial: {can_use_free_trial(test_user_id)}")
    print(f"Remaining uses: {get_remaining_free_uses(test_user_id)}")
    
    # Test usage increments
    for i in range(5):  # Try to use more than the limit
        if can_use_free_trial(test_user_id):
            new_count = increment_user_usage(test_user_id)
            remaining = get_remaining_free_uses(test_user_id)
            print(f"Use {i+1}: Count={new_count}, Remaining={remaining}")
        else:
            print(f"Use {i+1}: Free trial exhausted!")
    
    # Show final state
    print("\nFinal state:")
    print(f"Total usage count: {get_user_usage_count(test_user_id)}")
    print(f"Can use free trial: {can_use_free_trial(test_user_id)}")
    print(f"Remaining uses: {get_remaining_free_uses(test_user_id)}")
    
    # Show usage data file
    print("\nUsage data file contents:")
    usage_data = load_usage_data()
    print(json.dumps(usage_data, indent=2))

if __name__ == "__main__":
    test_free_trial_system()
