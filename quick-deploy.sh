#!/bin/bash

# Quick deployment script for new EC2 instance
# Run this directly on your new instance

set -e

echo "=== Quick EC2 Setup ==="
echo "This will set up a new instance with common configurations"
echo

# Basic system setup
echo "1. Updating system..."
sudo apt update && sudo apt upgrade -y

echo "2. Installing essential packages..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    htop \
    tree \
    unzip \
    vim \
    build-essential \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release

echo "3. Creating swap (2GB)..."
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "Swap created and enabled"
else
    echo "Swap already exists"
fi

echo "4. Setting up Python virtual environment..."
python3 -m venv ~/aws-env
source ~/aws-env/bin/activate
pip install --upgrade pip

echo "5. Installing common Python packages..."
pip install \
    boto3 \
    requests \
    pandas \
    numpy \
    python-dotenv \
    flask \
    fastapi \
    uvicorn \
    gunicorn \
    psutil \
    beautifulsoup4 \
    lxml

echo "6. Configuring bashrc..."
cat >> ~/.bashrc << 'EOF'

# Custom AWS Environment Setup
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'
alias grep='grep --color=auto'
alias fgrep='fgrep --color=auto'
alias egrep='egrep --color=auto'

# AWS Environment
alias activate='source ~/aws-env/bin/activate'
alias deactivate='deactivate'

# System info
alias meminfo='free -h'
alias diskinfo='df -h'
alias cpuinfo='lscpu'

# Python helpers
alias python='python3'
alias pip='pip3'

# Auto-activate virtual environment if it exists
if [ -d "$HOME/aws-env" ] && [ -z "$VIRTUAL_ENV" ]; then
    source ~/aws-env/bin/activate
fi

# Show system info on login (without exposing sensitive details)
echo "System: $(uname -sr)"
echo "Memory: $(free -h | grep ^Mem | awk '{print $3 "/" $2}')"
echo "Disk: $(df -h / | tail -1 | awk '{print $3 "/" $2 " (" $5 " used)"}')"
if [ -f /swapfile ]; then
    echo "Swap: $(free -h | grep ^Swap | awk '{print $2}')"
fi
echo "Python: $(python3 --version 2>/dev/null || echo 'Not installed')"
echo "Virtual Env: $([ ! -z "$VIRTUAL_ENV" ] && echo "Active ($(basename $VIRTUAL_ENV))" || echo "None")"
echo
EOF

echo "8. Setting up git and repositories..."
read -p "Enter your git username (or press Enter to skip): " git_user
read -p "Enter your git email (or press Enter to skip): " git_email

if [ ! -z "$git_user" ]; then
    git config --global user.name "$git_user"
fi
if [ ! -z "$git_email" ]; then
    git config --global user.email "$git_email"
fi

# Option to clone repositories
echo ""
read -p "Do you want to clone any Git repositories? (y/n): " clone_repos
if [ "$clone_repos" = "y" ] || [ "$clone_repos" = "Y" ]; then
    mkdir -p ~/projects
    echo "Enter repository URLs (one per line, empty line to finish):"
    while true; do
        read -p "Repository URL: " repo_url
        if [ -z "$repo_url" ]; then
            break
        fi
        
        # Extract repo name from URL
        repo_name=$(basename "$repo_url" .git)
        echo "Cloning $repo_name..."
        
        if git clone "$repo_url" ~/projects/"$repo_name"; then
            echo "Successfully cloned to ~/projects/$repo_name"
        else
            echo "Failed to clone $repo_url"
        fi
    done
fi

echo "9. Creating useful directories..."
mkdir -p ~/projects ~/scripts ~/logs

echo "10. Installing AWS CLI v2..."
if ! command -v aws &> /dev/null; then
    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
    unzip awscliv2.zip
    sudo ./aws/install
    rm -rf awscliv2.zip aws/
    echo "AWS CLI installed"
else
    echo "AWS CLI already installed"
fi

echo "11. Final setup..."
# Create a simple system info script
cat > ~/scripts/sysinfo.sh << 'EOF'
#!/bin/bash
echo "=== System Information ==="
echo "Hostname: [REDACTED]"
echo "OS: $(lsb_release -d | cut -f2)"
echo "Kernel: $(uname -r)"
echo "Uptime: $(uptime -p)"
echo "Load: $(uptime | awk -F'load average:' '{print $2}')"
echo
echo "=== Resources ==="
echo "CPU: $(nproc) cores"
echo "Memory: $(free -h | grep ^Mem | awk '{print $3 "/" $2 " (" int($3/$2*100) "%)"}')"
echo "Disk: $(df -h / | tail -1 | awk '{print $3 "/" $2 " (" $5 ")"}')"
echo "Swap: $(free -h | grep ^Swap | awk '{print $2}')"
echo
echo "=== Network ==="
echo "Network: Configured"
echo
echo "=== Python Environment ==="
echo "Python: $(python3 --version)"
echo "Virtual Env: $([ ! -z "$VIRTUAL_ENV" ] && echo "Active ($(basename $VIRTUAL_ENV))" || echo "None")"
if [ ! -z "$VIRTUAL_ENV" ]; then
    echo "Packages: $(pip list --format=freeze | wc -l) installed"
fi
EOF

chmod +x ~/scripts/sysinfo.sh

echo
echo "=== Setup Complete! ==="
echo "Instance is ready for use."
echo
echo "Useful commands:"
echo "  activate           - Activate Python virtual environment"
echo "  ~/scripts/sysinfo.sh - Show system information"
echo "  htop               - System monitor"
echo
echo "Next steps:"
echo "1. Source your new bashrc: source ~/.bashrc"
echo "2. Configure AWS credentials: aws configure"
echo "3. Install your specific Python packages: pip install -r requirements.txt"
echo "4. Check your cloned repositories in ~/projects/"
echo "5. Set up SSH keys for Git if needed: ssh-keygen -t ed25519 -C 'your_email@example.com'"
echo
echo "Your virtual environment is at: ~/aws-env"
echo "It will auto-activate when you log in."
