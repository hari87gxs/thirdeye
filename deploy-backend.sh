#!/bin/bash
# Deploy backend to EC2 with proper environment variables

set -e

echo "🔨 Building backend Docker image for linux/amd64..."
cd /Users/harikrishnan.r/Downloads/third-eye/backend
docker buildx build --platform linux/amd64 -t thirdeye-backend:latest .

echo "📦 Transferring image to EC2..."
docker save thirdeye-backend:latest | ssh -i ~/.ssh/thirdeye-debug.pem ec2-user@47.128.220.163 'sudo docker load'

echo "🔄 Restarting backend container with environment variables..."
ssh -i ~/.ssh/thirdeye-debug.pem ec2-user@47.128.220.163 'sudo docker stop thirdeye-backend 2>/dev/null || true && \
sudo docker rm thirdeye-backend 2>/dev/null || true && \
sudo docker run -d --name thirdeye-backend -p 8000:8000 \
  -e AZURE_OPENAI_API_KEY="fff41732e71b4239ba3a885f81a7d216" \
  -e AZURE_OPENAI_ENDPOINT="https://dsa-gpt4-dev.openai.azure.com/" \
  -e AZURE_OPENAI_API_VERSION="2024-12-01-preview" \
  -e AZURE_OPENAI_DEPLOYMENT="gpt-4o" \
  -e AZURE_OPENAI_VISION_DEPLOYMENT="gpt-4o" \
  -v /home/ec2-user/uploads:/app/uploads \
  -v /home/ec2-user/data:/app/data \
  thirdeye-backend:latest'

echo "⏳ Waiting for backend to start..."
sleep 3

echo "✅ Checking backend health..."
ssh -i ~/.ssh/thirdeye-debug.pem ec2-user@47.128.220.163 'curl -s localhost:8000/health'

echo ""
echo "🎉 Backend deployed successfully!"
echo "🌐 Access at: http://thirdeye-ec2-alb-1720575765.ap-southeast-1.elb.amazonaws.com"
