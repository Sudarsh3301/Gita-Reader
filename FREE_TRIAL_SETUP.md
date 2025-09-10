# Free Trial API Key System

This document explains how to set up and use the free trial system for the Gita application.

## Overview

The free trial system allows users to try the AI summarization feature 3 times before requiring them to input their own Groq API key. This is implemented using:

1. **Usage Tracking**: Each user gets a unique ID and their API usage is tracked
2. **Free Trial API Key**: A server-side API key that provides the free uses
3. **Graceful Degradation**: Clear messaging when trial is exhausted

## Setup Instructions

### 1. For Local Development

1. Get a Groq API key from https://console.groq.com/
2. Update `.streamlit/secrets.toml`:
   ```toml
   # Free trial API key (for hosting platform)
   groq_key = "your-actual-groq-api-key-here"
   
   # Regular API key (for fallback)
   GROQ_API_KEY = "your-groq-api-key-here"
   ```

### 2. For Production Deployment (Streamlit Cloud)

1. Go to your app's Settings > Secrets
2. Add the following in TOML format:
   ```toml
   groq_key = "your-free-trial-groq-api-key"
   GROQ_API_KEY = "your-fallback-groq-api-key"
   ```

### 3. For Other Hosting Platforms

The system reads the free trial API key from `st.secrets.groq_key`. Configure your hosting platform's secrets/environment variables accordingly.

## How It Works

### User Experience

1. **First Visit**: User sees "🎁 Free Trial: 3 uses remaining"
2. **Using Free Trial**: Click "Use Free Trial" button to activate
3. **After Each Use**: Counter decreases "🎁 Free Trial: 2 uses remaining"
4. **Trial Exhausted**: Shows "🚫 Free trial uses exhausted" with option to add own key
5. **Own API Key**: Users can always input their own key to bypass the trial

### Technical Implementation

1. **User Identification**: Each browser session gets a unique UUID
2. **Usage Tracking**: Stored in `usage_tracking.json` file
3. **API Wrapper**: `query_groq_with_usage_tracking()` handles trial logic
4. **Session State**: Tracks whether current session is using free trial

### File Structure

```
gita-deployment/
├── main.py                 # Main application with free trial logic
├── usage_tracking.json     # Auto-created usage tracking file
├── test_free_trial.py      # Test script for trial functionality
├── .streamlit/
│   └── secrets.toml        # Contains groq_key for free trial
└── FREE_TRIAL_SETUP.md     # This documentation
```

## Configuration Options

### Changing Free Trial Limit

In `main.py`, modify:
```python
FREE_TRIAL_USES = 3  # Change to desired number
```

### Usage Tracking File Location

In `main.py`, modify:
```python
USAGE_TRACKING_FILE = "usage_tracking.json"  # Change path if needed
```

## Testing

Run the test script to verify functionality:
```bash
cd gita-deployment
python test_free_trial.py
```

This will:
- Create a test user
- Simulate 5 API calls (exceeding the 3-use limit)
- Show usage tracking in action
- Display the usage data file contents

## Security Considerations

1. **API Key Protection**: Free trial key is stored in secrets, not in code
2. **Usage Limits**: Hard limit prevents abuse of free trial key
3. **User Tracking**: Uses session-based UUIDs, not personally identifiable information
4. **Graceful Fallback**: System continues working even if trial system fails

## Monitoring Usage

### Check Current Usage
The `usage_tracking.json` file contains all usage data:
```json
{
  "user-uuid-1": {
    "usage_count": 3,
    "first_use": "2024-01-15T10:30:00",
    "last_use": "2024-01-15T11:45:00"
  }
}
```

### Reset Usage (if needed)
To reset a user's trial:
1. Edit `usage_tracking.json`
2. Reduce their `usage_count` or delete their entry
3. Or delete the entire file to reset all users

## Troubleshooting

### "Free trial API key not configured on server"
- Check that `groq_key` is set in secrets
- Verify the API key is valid
- Ensure secrets are properly deployed

### Usage tracking not working
- Check file permissions for `usage_tracking.json`
- Verify the application can write to the deployment directory
- Check browser console for JavaScript errors

### API calls failing
- Verify the free trial API key has sufficient quota
- Check Groq API status
- Monitor rate limits

## User Interface Elements

The system adds these UI components:

1. **Free Trial Status**: Shows remaining uses
2. **Use Free Trial Button**: Activates trial for current session
3. **Own API Key Input**: Always available as alternative
4. **Usage Notifications**: Post-generation usage updates
5. **Exhaustion Warning**: Clear messaging when trial is done

## Best Practices

1. **Monitor API Usage**: Keep track of free trial API key usage
2. **Set Reasonable Limits**: 3 uses balances trial value with cost control
3. **Clear Communication**: Users understand the trial limitations
4. **Smooth Transition**: Easy path from trial to own API key
5. **Backup Plans**: System works even if trial features fail
