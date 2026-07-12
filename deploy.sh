#!/bin/bash
# Run this script to deploy the updated backend to Render
# Execute from: /home/samiransamanta/ULMIND/Pharmacy System/medical-store-backend

set -e

echo "📦 Staging all changes..."
git add -A

echo "📝 Committing..."
git commit -m "fix: add /auth/upsert endpoint, fix Clerk JWT middleware, fix JWKS URL derivation

- Added POST /api/auth/upsert endpoint that creates/updates MongoDB user from Clerk JWT claims
- Added get_clerk_payload dependency (does not require user in DB yet)
- Fixed JWKS URL to be dynamically derived from CLERK_PUBLISHABLE_KEY env var
- Added CLERK_PUBLISHABLE_KEY to settings.py
- Fixed auth middleware to handle email fallback correctly
- Added Live Clinic Queue routes and models"

echo "🚀 Pushing to GitHub (Render will auto-deploy)..."
git push origin main

echo "✅ Done! Render will deploy in ~2-3 minutes."
echo "   Watch: https://dashboard.render.com"
