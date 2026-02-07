# ThirdEye AI — AWS Deployment Guide

> Step-by-step instructions to deploy ThirdEye on AWS using **EC2 + Docker Compose** (simplest) or **ECS Fargate** (production-grade).

---

## Table of Contents

- [Option A: EC2 + Docker Compose (Recommended for Start)](#option-a-ec2--docker-compose-recommended-for-start)
- [Option B: ECS Fargate (Production-Grade)](#option-b-ecs-fargate-production-grade)
- [Domain & HTTPS Setup (Both Options)](#domain--https-setup)
- [Cost Estimation](#cost-estimation)
- [Environment Variables Reference](#environment-variables-reference)
- [Troubleshooting](#troubleshooting)

---

## Option A: EC2 + Docker Compose (Recommended for Start)

This is the simplest path — a single EC2 instance running both containers. Good for demos, POCs, and small teams.

### Prerequisites

- AWS account with console access
- A domain name (optional, but recommended for HTTPS)
- Your Azure OpenAI API key and endpoint

---

### Step 1: Launch an EC2 Instance

1. Go to **AWS Console → EC2 → Launch Instance**
2. Configure:

| Setting | Value |
|---------|-------|
| **Name** | `thirdeye-server` |
| **AMI** | Amazon Linux 2023 |
| **Instance type** | `t3.medium` (2 vCPU, 4 GB RAM) — minimum recommended |
| **Key pair** | Create new or use existing (you'll need this to SSH in) |
| **Network** | Default VPC, public subnet |
| **Storage** | 30 GB gp3 |

3. **Security Group** — Create or select with these inbound rules:

| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22 | TCP | Your IP | SSH access |
| 80 | TCP | 0.0.0.0/0 | HTTP |
| 443 | TCP | 0.0.0.0/0 | HTTPS |
| 3000 | TCP | 0.0.0.0/0 | Frontend (temporary, remove after setting up nginx) |
| 8000 | TCP | 0.0.0.0/0 | Backend API (temporary, remove after setting up nginx) |

4. Click **Launch Instance**

---

### Step 2: SSH into Your Instance

```bash
# Replace with your key file and instance public IP
ssh -i "your-key.pem" ec2-user@<YOUR-EC2-PUBLIC-IP>
```

---

### Step 3: Install Docker & Docker Compose

```bash
# Update system
sudo dnf update -y

# Install Docker
sudo dnf install docker -y
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ec2-user

# Install Docker Compose v2
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Install git
sudo dnf install git -y

# Log out and back in for docker group to take effect
exit
```

SSH back in:
```bash
ssh -i "your-key.pem" ec2-user@<YOUR-EC2-PUBLIC-IP>

# Verify
docker --version
docker compose version
```

---

### Step 4: Clone and Configure

```bash
# Clone the repo
git clone https://github.com/hari87gxs/thirdeye.git
cd thirdeye

# Create .env from example
cp .env.example .env

# Edit with your Azure OpenAI credentials
nano .env
```

Fill in your `.env`:
```env
AZURE_OPENAI_API_KEY=your-actual-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_VISION_DEPLOYMENT=gpt-4o
DATABASE_URL=sqlite:///./third_eye.db
ALLOWED_ORIGINS=http://<YOUR-EC2-PUBLIC-IP>:3000,http://localhost:3000
```

---

### Step 5: Update Frontend API URL and Build

The frontend needs to know where the backend is. Update the `docker-compose.yml` build arg:

```bash
# Edit docker-compose.yml — change the NEXT_PUBLIC_API_URL to your EC2 IP
nano docker-compose.yml
```

Change this line under `frontend > build > args`:
```yaml
NEXT_PUBLIC_API_URL: http://<YOUR-EC2-PUBLIC-IP>:8000/api
```

---

### Step 6: Build and Run

```bash
# Build and start (first time takes 3-5 minutes)
docker compose up --build -d

# Check status
docker compose ps

# View logs
docker compose logs -f
```

Expected output:
```
NAME                 STATUS                  PORTS
thirdeye-backend     Up (healthy)            0.0.0.0:8000->8000/tcp
thirdeye-frontend    Up                      0.0.0.0:3000->3000/tcp
```

---

### Step 7: Verify

```bash
# Test backend
curl http://localhost:8000/health

# Test from your browser
open http://<YOUR-EC2-PUBLIC-IP>:3000
```

🎉 **ThirdEye is now running on AWS!**

---

### Step 8: Set Up Nginx Reverse Proxy (Production)

This puts both services behind a single port 80/443 endpoint:

```bash
sudo dnf install nginx -y
sudo systemctl enable nginx
```

Create the config:
```bash
sudo tee /etc/nginx/conf.d/thirdeye.conf > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 50M;

    # Frontend
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # Backend health check
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }
}
EOF

sudo nginx -t && sudo systemctl start nginx
```

Now update the frontend to use the same origin for API calls:
```bash
# In docker-compose.yml, change NEXT_PUBLIC_API_URL:
# NEXT_PUBLIC_API_URL: /api   (relative URL — nginx proxies it)

# Also update ALLOWED_ORIGINS in .env:
# ALLOWED_ORIGINS=http://<YOUR-DOMAIN-OR-IP>

# Rebuild frontend
docker compose up --build -d frontend
```

Now remove ports 3000 and 8000 from your security group — everything goes through port 80.

---

### Step 9: Updates & Maintenance

```bash
cd ~/thirdeye

# Pull latest code
git pull

# Rebuild and restart
docker compose up --build -d

# View logs
docker compose logs -f backend
docker compose logs -f frontend

# Stop everything
docker compose down

# Stop and remove data (⚠️ deletes DB)
docker compose down -v
```

---

## Option B: ECS Fargate (Production-Grade)

For a fully managed, auto-scaling, no-SSH-needed deployment. More complex to set up but zero server maintenance.

### Architecture

```
Internet → ALB (port 80/443)
               ├── /api/*  → Backend Service (Fargate, port 8000)
               └── /*      → Frontend Service (Fargate, port 3000)
```

### Step 1: Push Images to ECR

```bash
# Create ECR repositories
aws ecr create-repository --repository-name thirdeye-backend
aws ecr create-repository --repository-name thirdeye-frontend

# Login to ECR
aws ecr get-login-password --region ap-southeast-1 | \
    docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com

# Build and push backend
cd backend
docker build -t thirdeye-backend .
docker tag thirdeye-backend:latest <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/thirdeye-backend:latest
docker push <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/thirdeye-backend:latest

# Build and push frontend
cd ../frontend
docker build --build-arg NEXT_PUBLIC_API_URL=https://your-domain.com/api -t thirdeye-frontend .
docker tag thirdeye-frontend:latest <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/thirdeye-frontend:latest
docker push <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/thirdeye-frontend:latest
```

### Step 2: Create ECS Cluster

```bash
aws ecs create-cluster --cluster-name thirdeye-cluster
```

### Step 3: Create Task Definitions

Create `backend-task.json`:
```json
{
  "family": "thirdeye-backend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::<ACCOUNT_ID>:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "backend",
      "image": "<ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/thirdeye-backend:latest",
      "portMappings": [{ "containerPort": 8000, "protocol": "tcp" }],
      "environment": [
        { "name": "DATABASE_URL", "value": "sqlite:///./third_eye.db" },
        { "name": "ALLOWED_ORIGINS", "value": "https://your-domain.com" }
      ],
      "secrets": [
        { "name": "AZURE_OPENAI_API_KEY", "valueFrom": "arn:aws:ssm:ap-southeast-1:<ACCOUNT_ID>:parameter/thirdeye/azure-openai-key" },
        { "name": "AZURE_OPENAI_ENDPOINT", "valueFrom": "arn:aws:ssm:ap-southeast-1:<ACCOUNT_ID>:parameter/thirdeye/azure-openai-endpoint" }
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\" || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/thirdeye-backend",
          "awslogs-region": "ap-southeast-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

Create `frontend-task.json`:
```json
{
  "family": "thirdeye-frontend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::<ACCOUNT_ID>:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "frontend",
      "image": "<ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/thirdeye-frontend:latest",
      "portMappings": [{ "containerPort": 3000, "protocol": "tcp" }],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/thirdeye-frontend",
          "awslogs-region": "ap-southeast-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

Register them:
```bash
aws ecs register-task-definition --cli-input-json file://backend-task.json
aws ecs register-task-definition --cli-input-json file://frontend-task.json
```

### Step 4: Create ALB & Target Groups

```bash
# Create ALB
aws elbv2 create-load-balancer \
    --name thirdeye-alb \
    --subnets subnet-xxx subnet-yyy \
    --security-groups sg-xxx

# Create target groups
aws elbv2 create-target-group --name thirdeye-backend-tg \
    --protocol HTTP --port 8000 --vpc-id vpc-xxx \
    --target-type ip --health-check-path /health

aws elbv2 create-target-group --name thirdeye-frontend-tg \
    --protocol HTTP --port 3000 --vpc-id vpc-xxx \
    --target-type ip --health-check-path /

# Create listener with rules
# Default → frontend, /api/* → backend
```

### Step 5: Create ECS Services

```bash
aws ecs create-service \
    --cluster thirdeye-cluster \
    --service-name thirdeye-backend \
    --task-definition thirdeye-backend \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
    --load-balancers "targetGroupArn=<BACKEND-TG-ARN>,containerName=backend,containerPort=8000"

aws ecs create-service \
    --cluster thirdeye-cluster \
    --service-name thirdeye-frontend \
    --task-definition thirdeye-frontend \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
    --load-balancers "targetGroupArn=<FRONTEND-TG-ARN>,containerName=frontend,containerPort=3000"
```

### Step 6: Store Secrets in SSM Parameter Store

```bash
aws ssm put-parameter --name /thirdeye/azure-openai-key \
    --type SecureString --value "your-actual-key"

aws ssm put-parameter --name /thirdeye/azure-openai-endpoint \
    --type SecureString --value "https://your-resource.openai.azure.com/"
```

---

## Domain & HTTPS Setup

### With EC2 (Certbot/Let's Encrypt)

```bash
# Install certbot
sudo dnf install certbot python3-certbot-nginx -y

# Get certificate (replace with your domain)
sudo certbot --nginx -d thirdeye.yourdomain.com

# Auto-renewal
sudo systemctl enable certbot-renew.timer
```

### With ECS (AWS Certificate Manager)

1. Go to **ACM → Request Certificate**
2. Enter your domain name
3. Validate via DNS (add CNAME to your domain)
4. Attach the certificate to your ALB listener on port 443

---

## Cost Estimation

### Option A: EC2 + Docker Compose

| Resource | Monthly Cost (ap-southeast-1) |
|----------|-------------------------------|
| EC2 t3.medium (on-demand) | ~$30 |
| EBS 30GB gp3 | ~$2.50 |
| Data transfer (10GB) | ~$1 |
| **Total** | **~$34/month** |

> 💡 **Save 60%** with a 1-year Reserved Instance: ~$13/month

### Option B: ECS Fargate

| Resource | Monthly Cost |
|----------|-------------|
| Backend (0.5 vCPU, 1GB) | ~$15 |
| Frontend (0.25 vCPU, 0.5GB) | ~$8 |
| ALB | ~$16 |
| ECR storage | ~$1 |
| Data transfer | ~$1 |
| **Total** | **~$41/month** |

> Note: Azure OpenAI costs are separate (~$0.005/1K tokens for GPT-4o).

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|:--------:|-------------|
| `AZURE_OPENAI_API_KEY` | ✅ | Your Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | ✅ | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_API_VERSION` | | API version (default: `2024-12-01-preview`) |
| `AZURE_OPENAI_DEPLOYMENT` | | Chat model deployment name (default: `gpt-4o`) |
| `AZURE_OPENAI_VISION_DEPLOYMENT` | | Vision model deployment name (default: `gpt-4o`) |
| `DATABASE_URL` | | SQLite connection string (default: `sqlite:///./third_eye.db`) |
| `ALLOWED_ORIGINS` | | Comma-separated CORS origins (default: `http://localhost:3000`) |
| `NEXT_PUBLIC_API_URL` | | Frontend build-time API URL (default: `http://localhost:8000/api`) |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Frontend can't reach backend** | Check `NEXT_PUBLIC_API_URL` matches your actual backend URL. Rebuild frontend after changing. |
| **CORS errors in browser** | Add your frontend URL to `ALLOWED_ORIGINS` in `.env` |
| **Container OOM killed** | Increase instance size (t3.medium → t3.large) or Fargate memory |
| **PDF processing slow** | pdf2image/poppler needs CPU. Use t3.medium minimum. |
| **"Permission denied" on uploads** | Check the uploads volume mount in docker-compose |
| **Health check failing** | `docker compose logs backend` — check Azure OpenAI credentials |
| **Images not building** | Ensure `.dockerignore` excludes `node_modules/` and `.venv/` |
| **Database lost on restart** | Ensure `backend-db` volume is mounted (check docker-compose.yml) |
