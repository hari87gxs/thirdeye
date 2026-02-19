#!/bin/bash
# Quick script to check Layout Agent logs from EC2

echo "🔍 Fetching Layout Agent logs from EC2..."
echo "================================================"

ssh -i ~/.ssh/thirdeye-debug.pem ec2-user@47.128.220.163 \
  'sudo docker logs --tail 200 thirdeye-backend 2>&1' | \
  grep -E "(Layout agent|📐|Extraction agent running|Using layout|Using bank from layout)" | \
  tail -30

echo "================================================"
echo "✅ Done! Upload a document to see Layout Agent in action."
