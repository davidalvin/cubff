#!/bin/bash

# Improved Script to capture current EC2 setup for replication
# Handles dependency conflicts better

echo "=== Capturing Current EC2 Setup (Improved) ==="
echo "Date: $(date)"
echo "Instance: $(curl -s http://169.254.169.254/latest/meta-data/instance-type 2>/dev/null || echo 'Local')"
echo

# Create output directory
mkdir -p ~/setup-capture
cd ~/setup-capture

echo "1. Capturing installed packages..."
dpkg --get-selections | grep -v deinstall | awk '{print $1}' > installed-packages.txt
apt list --installed 2>/dev/null | grep -E '\[installed\]' | cut -d'/' -f1 > apt-packages.txt

echo "2. Capturing Python environment (improved)..."

# Ensure Python and venv are available
if ! command -v python3 >/dev/null || ! python3 -m venv --help >/dev/null 2>&1; then
    echo "Error: Python3 and venv module are required but not found."
    exit 1
fi

# Create virtual environment if missing
if [ ! -d ~/aws-env ]; then
    echo "Creating virtual environment 'aws-env'..."
    python3 -m venv ~/aws-env
fi

# Activate virtual environment
echo "Activating 'aws-env'..."
source ~/aws-env/bin/activate

# Upgrade pip
pip install --upgrade pip



# Create multiple requirements files for better compatibility
echo "Creating requirements files..."

pip freeze > requirements-exact.txt

pip freeze | sed -E 's/(boto[^=]*)==[0-9.]+/\1/' \
           | sed -E 's/(aws[^=]*)==[0-9.]+/\1/' \
           | sed -E 's/(urllib3)==[0-9.]+/\1>=1.26.0/' \
           | sed -E 's/(certifi|six|python-dateutil)==[0-9.]+/\1/' \
           > requirements-relaxed.txt

pip freeze | grep -E '^(boto3|awscli|flask|django|requests|numpy|pandas|fastapi|uvicorn)' | \
           sed -E 's/==[0-9.]+$//' > requirements-core.txt

echo "# AWS packages" > requirements-grouped.txt
pip freeze | grep -E '^(boto|aws)' | sed -E 's/==[0-9.]+$//' >> requirements-grouped.txt
echo "" >> requirements-grouped.txt
echo "# Web frameworks" >> requirements-grouped.txt
pip freeze | grep -E '^(flask|django|fastapi|uvicorn|gunicorn)' | sed -E 's/==[0-9.]+$//' >> requirements-grouped.txt
echo "" >> requirements-grouped.txt
echo "# Data science" >> requirements-grouped.txt
pip freeze | grep -E '^(numpy|pandas|scipy|matplotlib|seaborn|jupyter)' | sed -E 's/==[0-9.]+$//' >> requirements-grouped.txt
echo "" >> requirements-grouped.txt
echo "# Other packages" >> requirements-grouped.txt
pip freeze | grep -vE '^(boto|aws|flask|django|fastapi|uvicorn|gunicorn|numpy|pandas|scipy|matplotlib|seaborn|jupyter)' | sed -E 's/==[0-9.]+$//' >> requirements-grouped.txt

python --version > python-version.txt
deactivate

echo "3. Capturing full .bashrc..."
cp ~/.bashrc bashrc-full.txt

echo "4. Capturing swap configuration..."
swapon --show > swap-info.txt
free -h >> swap-info.txt
if [ -f /swapfile ]; then
    ls -lh /swapfile >> swap-info.txt
    echo "Swapfile exists" >> swap-info.txt
fi

echo "5. Capturing system services and processes..."
systemctl list-units --type=service --state=running | grep -v "^UNIT" | head -20 > running-services.txt

echo "6. Capturing network and security..."
if command -v aws &> /dev/null; then
    INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null)
    if [ ! -z "$INSTANCE_ID" ]; then
        aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[*].Instances[*].SecurityGroups[*]' > security-groups.json 2>/dev/null || echo "Could not fetch security groups"
    fi
fi

echo "7. Capturing Git repositories..."
echo "Scanning for Git repositories..."
find ~ -type d -name ".git" 2>/dev/null | while read gitdir; do
    repo_path=$(dirname "$gitdir")
    echo "Found repo: $repo_path"
    
    cd "$repo_path"
    repo_name=$(basename "$repo_path")
    
    remote_url=$(git remote get-url origin 2>/dev/null || git remote get-url $(git remote | head -1) 2>/dev/null || echo "no-remote")
    current_branch=$(git branch --show-current 2>/dev/null || echo "unknown")
    last_commit=$(git log -1 --format="%h - %s" 2>/dev/null || echo "no-commits")
    
    if git diff --quiet && git diff --staged --quiet 2>/dev/null; then
        status="clean"
    else
        status="uncommitted-changes"
        git status --porcelain > "$HOME/setup-capture/git-changes-${repo_name}.txt" 2>/dev/null
    fi
    
    echo "$repo_path|$remote_url|$current_branch|$status|$last_commit" >> ~/setup-capture/git-repos.txt
done

if [ -f ~/setup-capture/git-repos.txt ]; then
    echo "Git Repositories Found:" > ~/setup-capture/git-summary.txt
    echo "======================" >> ~/setup-capture/git-summary.txt
    while IFS='|' read -r path url branch status commit; do
        echo "Repository: $(basename "$path")" >> ~/setup-capture/git-summary.txt
        echo "  Path: $path" >> ~/setup-capture/git-summary.txt
        echo "  URL: $url" >> ~/setup-capture/git-summary.txt
        echo "  Branch: $branch" >> ~/setup-capture/git-summary.txt
        echo "  Status: $status" >> ~/setup-capture/git-summary.txt
        echo "  Last Commit: $commit" >> ~/setup-capture/git-summary.txt
        echo "" >> ~/setup-capture/git-summary.txt
    done < ~/setup-capture/git-repos.txt
else
    echo "No Git repositories found" > ~/setup-capture/git-summary.txt
fi

echo "8. Capturing custom configurations..."
[ -f ~/.ssh/config ] && cp ~/.ssh/config ssh-config.txt
[ -f ~/.gitconfig ] && cp ~/.gitconfig gitconfig.txt
[ -f ~/.vimrc ] && cp ~/.vimrc vimrc.txt

echo "9. Creating setup summary..."
cat > setup-summary.txt << EOF
EC2 Setup Summary
Generated: $(date)
Instance Type: $(curl -s http://169.254.169.254/latest/meta-data/instance-type 2>/dev/null || echo 'Local')
Ubuntu Version: $(lsb_release -d 2>/dev/null | cut -f2 || echo 'Unknown')
Python Version: $(cat python-version.txt)
Virtual Environment: $([ -d ~/aws-env ] && echo "Yes (aws-env)" || echo "No")
Swap: $([ -f /swapfile ] && echo "Yes" || echo "No")
Git Repositories: $([ -f git-repos.txt ] && wc -l < git-repos.txt || echo "0")

Python Requirements Files Created:
- requirements-exact.txt (exact versions - may have conflicts)
- requirements-relaxed.txt (relaxed versions - recommended)
- requirements-core.txt (core packages only)
- requirements-grouped.txt (organized by category)

Recommendation: Use requirements-relaxed.txt for the best compatibility
EOF

echo "10. Generating improved automated setup script..."
cat > setup-new-instance.sh << 'SCRIPT_EOF'
#!/bin/bash

# Improved Automated EC2 Setup Script
# Handles dependency conflicts better

set -e  # Exit on any error

echo "=== Setting up new EC2 instance (Improved) ==="
echo "Starting at: $(date)"

# Update system
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install captured packages
echo "Installing system packages..."
if [ -f apt-packages.txt ]; then
    sudo apt install -y python3 python3-pip python3-venv git curl wget htop
    
    while read package; do
        if [ ! -z "$package" ]; then
            sudo apt install -y "$package" 2>/dev/null || echo "Warning: Could not install $package"
        fi
    done < apt-packages.txt
fi

# Create swap if it was configured
echo "Setting up swap..."
if grep -q "Swapfile exists" swap-info.txt 2>/dev/null; then
    if [ ! -f /swapfile ]; then
        echo "Creating 2GB swapfile..."
        sudo fallocate -l 2G /swapfile
        sudo chmod 600 /swapfile
        sudo mkswap /swapfile
        sudo swapon /swapfile
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
        echo "Swap created and enabled"
    else
        echo "Swapfile already exists"
    fi
fi

# Set up Python virtual environment
echo "Setting up Python virtual environment..."
python3 -m venv ~/aws-env
source ~/aws-env/bin/activate

# Install Python packages with fallback strategy
echo "Installing Python packages..."
pip install --upgrade pip

# Try different requirements files in order of preference
if [ -f requirements-relaxed.txt ] && [ -s requirements-relaxed.txt ]; then
    echo "Trying relaxed requirements first..."
    if pip install -r requirements-relaxed.txt; then
        echo "✓ Successfully installed packages from requirements-relaxed.txt"
    else
        echo "⚠ Failed with relaxed requirements, trying core packages..."
        if [ -f requirements-core.txt ] && [ -s requirements-core.txt ]; then
            pip install -r requirements-core.txt || echo "Some core packages failed to install"
        fi
        echo "Installing essential AWS packages..."
        pip install boto3 awscli requests || echo "Failed to install some essential packages"
    fi
elif [ -f requirements-core.txt ] && [ -s requirements-core.txt ]; then
    echo "Installing core packages..."
    pip install -r requirements-core.txt
    echo "Installing essential packages..."
    pip install boto3 awscli requests
elif [ -f requirements.txt ] && [ -s requirements.txt ]; then
    echo "Trying exact requirements (may fail due to conflicts)..."
    pip install -r requirements.txt || {
        echo "⚠ Exact requirements failed, installing essential packages..."
        pip install boto3 awscli requests
    }
else
    echo "No requirements file found, installing common packages..."
    pip install boto3 awscli requests
fi

# Restore full bashrc
echo "Restoring .bashrc..."
if [ -f bashrc-full.txt ]; then
    cp bashrc-full.txt ~/.bashrc
    chown "$USER:$USER" ~/.bashrc 2>/dev/null || true
fi

# Restore config files
echo "Restoring configuration files..."
[ -f gitconfig.txt ] && cp gitconfig.txt ~/.gitconfig
[ -f vimrc.txt ] && cp vimrc.txt ~/.vimrc
[ -f ssh-config.txt ] && mkdir -p ~/.ssh && cp ssh-config.txt ~/.ssh/config && chmod 600 ~/.ssh/config

# Clone Git repositories
echo "Cloning Git repositories..."
if [ -f git-repos.txt ]; then
    mkdir -p ~/projects
    while IFS='|' read -r original_path remote_url current_branch status last_commit; do
        if [ "$remote_url" != "no-remote" ]; then
            repo_name=$(basename "$original_path")
            
            echo "Cloning $repo_name from $remote_url..."
            if git clone "$remote_url" "$HOME/projects/$repo_name"; then
                cd "$HOME/projects/$repo_name"
                
                if [ "$current_branch" != "main" ] && [ "$current_branch" != "master" ] && [ "$current_branch" != "unknown" ]; then
                    git checkout "$current_branch" 2>/dev/null || echo "Could not switch to branch $current_branch"
                fi
                
                echo "Successfully cloned $repo_name to ~/projects/$repo_name"
                
                if [ "$status" = "uncommitted-changes" ] && [ -f "../setup-capture/git-changes-${repo_name}.txt" ]; then
                    echo "Warning: Original repo had uncommitted changes. See git-changes-${repo_name}.txt"
                fi
            else
                echo "Failed to clone $repo_name - you may need to set up SSH keys or authentication"
            fi
        else
            echo "Skipping $(basename "$original_path") - no remote URL found"
        fi
    done < git-repos.txt
    cd ~/setup-capture
else
    echo "No Git repositories to clone"
fi

deactivate

echo "=== Setup Complete ==="
echo "Finished at: $(date)"
echo ""
echo "Next steps:"
echo "1. Activate virtual environment: source ~/aws-env/bin/activate"
echo "2. Source updated bashrc: source ~/.bashrc"
echo "3. Verify setup: python --version && pip list"
echo ""
echo "Package installation notes:"
echo "- Used relaxed version requirements to avoid dependency conflicts"
echo "- Some packages may be newer versions than the original"
echo "- Check 'pip list' to verify all needed packages are installed"
echo ""
echo "Don't forget to:"
echo "- Update your SSH keys for Git access"
echo "- Configure AWS credentials if needed"
echo "- Update security groups to match your previous instance"
echo "- Check cloned repositories in ~/projects/"
SCRIPT_EOF

chmod +x setup-new-instance.sh

echo
echo "=== Improved Capture Complete ==="
echo "Files created in ~/setup-capture/:"
ls -la ~/setup-capture/
echo
echo "Requirements files created:"
echo "- requirements-relaxed.txt (recommended - avoids version conflicts)"
echo "- requirements-core.txt (essential packages only)"
echo "- requirements-exact.txt (exact versions - may have conflicts)"
echo "- requirements-grouped.txt (organized by category)"
echo
echo "The setup script will try requirements files in this order:"
echo "1. requirements-relaxed.txt (best compatibility)"
echo "2. requirements-core.txt (fallback)"
echo "3. Essential packages (boto3, awscli, requests)"


