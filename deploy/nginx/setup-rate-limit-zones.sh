#!/bin/bash
# Script to ensure rate limiting zones are included in the main nginx configuration

set -e

RATE_LIMIT_INCLUDE="include /etc/nginx/snippets/rate-limit-zones.conf;"
NGINX_CONF="/etc/nginx/nginx.conf"

# Check if the include is already present
if grep -q "$RATE_LIMIT_INCLUDE" "$NGINX_CONF"; then
    echo "Rate limit zones include already present in nginx.conf"
    exit 0
fi

# Find the line with conf.d include and add the rate limit include after it
if grep -q "include /etc/nginx/conf.d/\*.conf;" "$NGINX_CONF"; then
    sudo sed -i '/include \/etc\/nginx\/conf.d\/\*.conf;/a \\tinclude /etc/nginx/snippets/rate-limit-zones.conf;' "$NGINX_CONF"
    echo "Added rate limit zones include to nginx.conf"
else
    echo "Could not find conf.d include line in nginx.conf"
    exit 1
fi

# Test nginx configuration
if sudo nginx -t; then
    echo "Nginx configuration test passed"
else
    echo "Nginx configuration test failed, rolling back"
    sudo sed -i '/include \/etc\/nginx\/snippets\/rate-limit-zones.conf;/d' "$NGINX_CONF"
    exit 1
fi
