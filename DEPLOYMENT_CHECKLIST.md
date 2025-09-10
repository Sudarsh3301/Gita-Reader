# Deployment Checklist for Free Trial System

## Pre-Deployment Setup

### 1. API Keys
- [ ] Obtain a Groq API key for free trial from https://console.groq.com/
- [ ] Test the API key works with a simple request
- [ ] Decide on usage limits for the free trial key

### 2. Hosting Platform Configuration

#### For Streamlit Cloud:
- [ ] Go to App Settings > Secrets
- [ ] Add the following secrets in TOML format:
  ```toml
  groq_key = "your-free-trial-groq-api-key"
  GROQ_API_KEY = "your-fallback-groq-api-key"
  ```

#### For Other Platforms:
- [ ] Configure environment variables or secrets management
- [ ] Ensure the app can read `st.secrets.groq_key`
- [ ] Test secrets are accessible in the deployment environment

### 3. File Permissions
- [ ] Ensure the app can create and write to `usage_tracking.json`
- [ ] Verify the deployment directory has write permissions
- [ ] Test file creation in the deployment environment

## Deployment Steps

### 1. Code Deployment
- [ ] Deploy the updated `main.py` with free trial functionality
- [ ] Deploy the updated `.streamlit/secrets.toml` (for local testing)
- [ ] Include `FREE_TRIAL_SETUP.md` and this checklist

### 2. Configuration
- [ ] Set the `groq_key` secret in your hosting platform
- [ ] Verify `FREE_TRIAL_USES = 3` is set correctly
- [ ] Confirm `USAGE_TRACKING_FILE = "usage_tracking.json"` path

### 3. Testing
- [ ] Test the app loads without errors
- [ ] Verify free trial UI appears correctly
- [ ] Test "Use Free Trial" button functionality
- [ ] Confirm usage tracking works (check file creation)
- [ ] Test trial exhaustion behavior
- [ ] Verify own API key input still works

## Post-Deployment Verification

### 1. User Experience Testing
- [ ] Open app in incognito/private browser window
- [ ] Verify "🎁 Free Trial: 3 uses remaining" appears
- [ ] Click "Use Free Trial" and confirm it activates
- [ ] Generate AI summaries and verify they work
- [ ] Check usage counter decreases correctly
- [ ] Test until trial is exhausted
- [ ] Verify "🚫 Free trial exhausted" message appears
- [ ] Test own API key input works after trial exhaustion

### 2. Technical Verification
- [ ] Check `usage_tracking.json` file is created
- [ ] Verify usage data is being recorded correctly
- [ ] Test multiple users (different browser sessions)
- [ ] Confirm each user gets their own usage tracking
- [ ] Monitor API usage on Groq dashboard

### 3. Error Handling
- [ ] Test with invalid free trial API key
- [ ] Test with no API key configured
- [ ] Test file write permission errors
- [ ] Verify graceful fallbacks work

## Monitoring and Maintenance

### 1. Usage Monitoring
- [ ] Set up monitoring for free trial API key usage
- [ ] Monitor the `usage_tracking.json` file size
- [ ] Track number of unique users using free trial
- [ ] Monitor conversion rate from trial to own API key

### 2. API Key Management
- [ ] Monitor Groq API quota for free trial key
- [ ] Set up alerts for high usage
- [ ] Plan for API key rotation if needed
- [ ] Monitor costs and usage patterns

### 3. Regular Maintenance
- [ ] Periodically clean up old usage tracking data
- [ ] Review and adjust free trial limits if needed
- [ ] Update documentation as needed
- [ ] Monitor user feedback about the trial experience

## Troubleshooting Common Issues

### "Free trial API key not configured on server"
1. Check secrets configuration in hosting platform
2. Verify `groq_key` is set correctly
3. Restart the application if needed

### Usage tracking not working
1. Check file write permissions
2. Verify deployment directory is writable
3. Check for any file system restrictions

### API calls failing
1. Verify free trial API key is valid
2. Check Groq API status and quotas
3. Monitor rate limits and usage

### UI not showing correctly
1. Clear browser cache
2. Check for JavaScript errors in console
3. Verify Streamlit session state is working

## Success Criteria

- [ ] New users see free trial option immediately
- [ ] Free trial provides 3 working AI summary generations
- [ ] Usage tracking accurately counts and limits usage
- [ ] Clear messaging guides users through trial and beyond
- [ ] Smooth transition to own API key when trial exhausted
- [ ] No errors or crashes during normal usage
- [ ] System works for multiple concurrent users

## Rollback Plan

If issues occur:
1. Revert to previous version without free trial
2. Remove free trial UI elements
3. Fall back to original API key input only
4. Investigate and fix issues in staging environment
5. Redeploy with fixes

## Contact Information

- Groq API Support: https://console.groq.com/
- Streamlit Documentation: https://docs.streamlit.io/
- Application Repository: [Your repo URL]
