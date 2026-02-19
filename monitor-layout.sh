#!/bin/bash
# Monitor Layout Agent activity on EC2

echo "🔍 Layout Agent Monitor"
echo "======================="
echo ""

# Check if we want live monitoring or past logs
if [ "$1" == "live" ]; then
    echo "📡 Starting LIVE monitoring (Press Ctrl+C to stop)..."
    echo "Upload a document to see Layout Agent in action!"
    echo ""
    ssh -i ~/.ssh/thirdeye-debug.pem ec2-user@47.128.220.163 \
        'sudo docker logs -f thirdeye-backend 2>&1 | grep --line-buffered -E "Layout agent|📐|🏦|📊|Extraction agent|confidence|Using layout|Using bank from layout"'
else
    echo "📊 Recent Layout Agent Activity (last 50 lines):"
    echo ""
    ssh -i ~/.ssh/thirdeye-debug.pem ec2-user@47.128.220.163 \
        'sudo docker logs --tail 200 thirdeye-backend 2>&1' | \
        grep -E "Layout agent|📐|🏦|📊|Extraction agent|confidence|Using layout|Using bank from layout" | \
        tail -50
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "💡 Tip: Run './monitor-layout.sh live' for real-time monitoring"
fi
