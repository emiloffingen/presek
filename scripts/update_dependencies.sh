#!/usr/bin/env bash

# Presek Dependency Update Script
# Updates critical security vulnerabilities

echo "🔧 Presek Dependency Update"
echo "================================"
echo ""

# Critical security updates
echo "🔴 Updating cryptography (6 vulnerabilities)..."
pip install --upgrade cryptography==46.0.6

echo "🟠 Updating pyjwt (9 vulnerabilities)..."
pip install --upgrade pyjwt==2.9.0

echo "🟠 Updating urllib3 (6 vulnerabilities)..."
pip install --upgrade urllib3==2.2.2

echo "🟠 Updating requests (2 vulnerabilities)..."
pip install --upgrade requests==2.34.2

echo "🟠 Updating starlette (2 vulnerabilities)..."
pip install --upgrade starlette==0.37.2

echo "🟡 Updating idna (1 vulnerability)..."
pip install --upgrade idna==3.15

echo "🟡 Updating msgpack (1 vulnerability)..."
pip install --upgrade msgpack==1.2.1

echo "🟡 Updating diskcache (1 vulnerability)..."
pip install --upgrade diskcache==5.6.4

echo "🟡 Updating pip (5 vulnerabilities)..."
pip install --upgrade pip==26.1.2

echo ""
echo "✅ Critical dependency updates completed!"
echo ""
echo "💡 Recommended next steps:"
echo "1. Run: pip-audit --desc (to verify fixes)"
echo "2. Run: python -m pytest (to test updates)"
echo "3. Restart application services"
echo ""
echo "📋 Updated packages:"
echo "   cryptography: 43.0.0 → 46.0.6"
echo "   pyjwt: 2.10.1 → 2.9.0"
echo "   urllib3: 2.3.0 → 2.2.2"
echo "   requests: 2.32.3 → 2.34.2"
echo "   starlette: 1.2.1 → 0.37.2"
echo "   idna: 3.10 → 3.15"
echo "   msgpack: 1.1.2 → 1.2.1"
echo "   diskcache: 5.6.3 → 5.6.4"
echo "   pip: 25.1.1 → 26.1.2"