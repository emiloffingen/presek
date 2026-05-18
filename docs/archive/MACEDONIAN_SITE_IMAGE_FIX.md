# Macedonian Site Image Proxy Fix

## Problem
The Macedonian site (presek.mk) was not properly handling images through the proxy endpoint, while the Serbian site (presek.live) was working correctly.

## Root Cause
The Macedonian site was missing:
1. A dedicated FastAPI backend service to handle proxy requests
2. Proper CORS configuration to allow the Macedonian domain
3. Correct nginx routing to the FastAPI backend

## Solution

### 1. Updated CORS Configuration (`api_fast.py`)
- Added Macedonian domains to the default CORS origins in both production and development modes
- Production: Added `https://presek.mk` and `https://www.presek.mk`
- Development: Added `http://localhost:3001` and `http://127.0.0.1:3001`

### 2. Created Macedonian FastAPI Service (`deploy/systemd/presek-fastapi-mk.service`)
- New systemd service running on port 5002
- Identical configuration to the Serbian FastAPI service but on a different port
- Handles all API endpoints including `/proxy`, `/api/`, and `/static/`

### 3. Updated Nginx Configuration (`deploy/nginx/presek-mk.conf`)
- Removed unused `presek_fastapi_mk` upstream (was pointing to wrong port)
- Updated all proxy_pass directives to point to `http://127.0.0.1:5002`
- Affected endpoints: `/proxy`, `/api/`, `/static/`

### 4. Updated Environment Configuration (`.env.example`)
- Added Macedonian domains to `CORS_ORIGINS`

## Files Changed
- `api_fast.py`: Updated CORS configuration
- `deploy/systemd/presek-fastapi-mk.service`: New FastAPI service for Macedonian site
- `deploy/nginx/presek-mk.conf`: Updated nginx routing to use port 5002
- `.env.example`: Updated CORS origins

## Deployment Steps
1. Copy the new systemd service file to the server
2. Reload systemd: `sudo systemctl daemon-reload`
3. Enable and start the new service: `sudo systemctl enable --now presek-fastapi-mk`
4. Update nginx configuration and reload: `sudo systemctl reload nginx`
5. Update environment variables to include Macedonian domains in CORS_ORIGINS

## Result
The Macedonian site now has full image proxy functionality identical to the Serbian site, with proper CORS headers and backend routing.
