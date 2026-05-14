# 🖼️ Image Proxy Troubleshooting Guide

## Common Issues and Solutions

### 1. **Blank Image Placeholders (Black/Empty Areas)**

**Symptoms**: Image areas below article cards are completely black or empty.

**Root Causes & Solutions**:

#### A. Hotlinking Blocked (HTTP 403)
- **Symptom**: Proxy returns fallback SVG with "hotlink_blocked" reason
- **Diagnosis**: Check proxy response headers for `X-Proxy-Fallback: hotlink_blocked_403`
- **Solution**: 
  ```python
  # The proxy now automatically retries with proper Referer header
  # If still blocked, you may need to:
  # 1. Contact the source site for permission
  # 2. Cache images locally (see local_image_path in database)
  # 3. Use a different CDN or image source
  ```

#### B. Invalid/Broken Image URLs (HTTP 404)
- **Symptom**: Proxy returns fallback SVG with "not_found" reason
- **Diagnosis**: Check proxy response headers for `X-Proxy-Fallback: not_found`
- **Solution**:
  ```python
  # Fix the API response parser to extract valid image URLs
  # Common issues:
  # - Relative URLs (should be absolute)
  # - Placeholder URLs (e.g., "no-image.png")
  # - Broken scraping logic
  ```

#### C. Proxy Service Unavailable
- **Symptom**: 502 Bad Gateway or connection refused
- **Diagnosis**: Check nginx error logs for "Connection refused"
- **Solution**:
  ```bash
  # Restart the FastAPI service
  systemctl restart presek_fastapi
  
  # Check service status
  systemctl status presek_fastapi
  
  # Verify port is listening
  ss -tlnp | grep 5001
  ```

#### D. CORS Issues
- **Symptom**: Images load in proxy but not in browser
- **Diagnosis**: Check browser console for CORS errors
- **Solution**: The proxy already handles CORS by serving images from your domain

### 2. **Diagnostic Information**

The enhanced proxy now provides detailed diagnostic information:

#### Response Headers
- `X-Proxy-Fallback`: Reason for fallback (e.g., "not_found", "hotlink_blocked_403")
- `X-Debug-Reason`: Same as above for debugging
- `X-Diagnostic-Info`: Detailed information about the failure

#### SVG Fallback Content
The fallback SVG now includes diagnostic text at the bottom:
- "Proxy Fallback: [reason]"
- "URL: [truncated_url]"

### 3. **Testing the Proxy**

#### Test with Working Image
```bash
curl -s "http://localhost:5001/proxy?url=https://httpbin.org/image/png&w=400" | file -
# Expected: RIFF (little-endian) data, Web/P image...
```

#### Test with Broken Image
```bash
curl -s "http://localhost:5001/proxy?url=https://example.com/nonexistent.jpg&w=400" | grep "Proxy Fallback"
# Expected: Shows diagnostic SVG with error reason
```

#### Test Headers
```bash
curl -I "http://localhost:5001/proxy?url=https://httpbin.org/image/png&w=400"
# Check for: X-Proxy-Fallback, X-Debug-Reason headers
```

### 4. **Common Fixes**

#### Fix Relative URLs
```python
# In your API response parser:
def fix_relative_urls(text, base_url):
    if text.startswith('/'):
        return f"{base_url.rstrip('/')}/{text.lstrip('/')}
    return text
```

#### Handle Hotlinking Protection
```python
# The proxy now automatically:
# 1. Sets proper User-Agent
# 2. Includes Referer header
# 3. Retries with source domain referer on 403
```

#### Validate Image URLs
```python
# Enhanced validation in routes/system.py:
- Checks for missing domains
- Blocks localhost/loopback addresses
- Validates URL length
- Ensures proper HTTP/HTTPS scheme
```

### 5. **Monitoring and Logging**

#### Check Proxy Logs
```bash
# FastAPI logs
journalctl -u presek_fastapi -f | grep "\[proxy\]"

# Nginx logs
tail -f /var/log/nginx/error.log | grep proxy
```

#### Key Log Messages
- `[proxy] Hotlinking blocked for [url]` - Hotlink protection triggered
- `[proxy] Serving fallback for [url]: [reason]` - Fallback served
- `[proxy] Error for [url]: [exception]` - Proxy error occurred

### 6. **Performance Optimization**

#### Cache Hit Rate
```bash
# Check Redis for cached images
redis-cli keys "proxy:bin:*" | wc -l
```

#### Cache TTL
- Images cached for 24 hours (86400 seconds)
- Fallbacks cached for 1 hour (3600 seconds)

### 7. **Fallback Behavior**

The proxy serves SVG fallbacks for:
- 403 Forbidden (hotlinking blocked)
- 404 Not Found (broken URLs)
- Timeout errors (slow responses)
- Invalid content types
- Size limits exceeded
- Security blocks

### 8. **Troubleshooting Checklist**

1. [ ] Test proxy directly with `curl`
2. [ ] Check proxy response headers for diagnostic info
3. [ ] Examine nginx error logs
4. [ ] Verify FastAPI service is running
5. [ ] Test with known working image URL
6. [ ] Check browser console for CORS errors
7. [ ] Validate image URLs from API responses
8. [ ] Review proxy logs for specific errors

### 9. **Contact & Support**

For persistent issues:
- Check the [AUDIT_REPORT.md](./AUDIT_REPORT.md) for system status
- Review [BUG_REPORT_SUMMARY.md](./BUG_REPORT_SUMMARY.md) for known issues
- Consult the deployment documentation in `docs/`

---
*Last updated: 2024-05-14* 🛠️