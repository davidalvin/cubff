#!/bin/bash

# Script to capture current EC2 setup for replication
# Run this on your current 4GB instance

echo "=== Capturing Current EC2 Setup ==="
echo "Date: $(date)"
echo "Instance: $(curl -s http://169.254.169.254/latest/meta-data/instance-type 2>/dev/null || echo 'Local')"
echo

# Create output directory
mkdir -p ~/setup-capture
cd ~/setup-capture

echo "1. Capturing installed packages..."
# Get explicitly installed packages (not dependencies)
dpkg --get-selections | grep -v deinstall | awk '{print $1}' > installed-packages.txt
apt list --installed 2>/dev/null | grep -E '\[installed\]' | cut -d'/' -f1 > apt-packages.txt

echo "2. Capturing Python environment..."
# Check if virtual environment exists
if [ -d ~/aws-env ]; then
    echo "Virtual environment 'aws-env' found"
    source ~/aws-env/bin/activate
    pip freeze > requirements.txt
    python --version > python-version.txt
    deactivate
else
    echo "Virtual environment 'aws-env' not found - checking global Python"
    pip freeze > requirements-global.txt 2>/dev/null || echo "No pip packages found"
    python3 --version > python-version.txt 2>/dev/null || echo "Python3 not found"
fi

echo "3. Capturing bashrc customizations..."
# Extract custom additions from bashrc (everything after a common marker or last 50 lines)
tail -50 ~/.bashrc > bashrc-additions.txt

echo "4. Capturing swap configuration..."
# Check current swap
swapon --show > swap-info.txt
free -h >> swap-info.txt
# Check if there's a swapfile
if [ -f /swapfile ]; then
    ls -lh /swapfile >> swap-info.txt
    echo "Swapfile exists" >> swap-info.txt
fi

echo "5. Capturing system services and processes..."
systemctl list-units --type=service --state=running | grep -v "^UNIT" | head -20 > running-services.txt

echo "6. Capturing network and security..."
# Security groups (if AWS CLI is available)
if command -v aws &> /dev/null; then
    INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null)
    if [ ! -z "$INSTANCE_ID" ]; then
        aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[*].Instances[*].SecurityGroups[*]' > security-groups.json 2>/dev/null || echo "Could not fetch security groups"
    fi
fi

echo "7. Capturing Git repositories..."
# Find all git repositories
echo "Scanning for Git repositories..."
find ~ -type d -name ".git" 2>/dev/null | while read gitdir; do
    repo_path=$(dirname "$gitdir")
    echo "Found repo: $repo_path"
    
    # Get repository info
    cd "$repo_path"
    repo_name=$(basename "$repo_path")
    
    # Get remote URLs (origin priority)
    remote_url=$(git remote get-url origin 2>/dev/null || git remote get-url $(git remote | head -1) 2>/dev/null || echo "no-remote")
    current_branch=$(git branch --show-current 2>/dev/null || echo "unknown")
    last_commit=$(git log -1 --format="%h - %s" 2>/dev/null || echo "no-commits")
    
    # Check for uncommitted changes
    if git diff --quiet && git diff --staged --quiet 2>/dev/null; then
        status="clean"
    else
        status="uncommitted-changes"
        git status --porcelain > "$HOME/setup-capture/git-changes-${repo_name}.txt" 2>/dev/null
    fi
    
    # Save repo info
    echo "$repo_path|$remote_url|$current_branch|$status|$last_commit" >> ~/setup-capture/git-repos.txt
done

# Create repositories summary
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
# Common config files
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

Key Files Generated:
- requirements.txt (Python packages)
- apt-packages.txt (System packages)
- bashrc-additions.txt (Shell customizations)
- swap-info.txt (Swap configuration)
- git-repos.txt (Repository information)
- setup-new-instance.sh (Automated setup script)
EOF

echo "10. Generating automated setup script..."
cat > setup-new-instance.sh << 'SCRIPT_EOF'
#!/bin/bash

# Automated EC2 Setup Script
# Generated from capture-setup.sh

set -e  # Exit on any error

echo "=== Setting up new EC2 instance ==="
echo "Starting at: $(date)"

# Update system
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install captured packages
echo "Installing system packages..."
if [ -f apt-packages.txt ]; then
    # Install essential packages first
    sudo apt install -y python3 python3-pip python3-venv git curl wget htop
    
    # Install other captured packages (with error handling)
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

# Install Python packages
if [ -f requirements.txt ]; then
    echo "Installing Python packages..."
    pip install --upgrade pip
    pip install -r requirements.txt
else
    echo "No requirements.txt found, installing common packages..."
    pip install --upgrade pip boto3 requests
fi

# Apply bashrc customizations
echo "Applying bashrc customizations..."
if [ -f bashrc-additions.txt ]; then
    echo "" >> ~/.bashrc
    echo "# Custom additions (restored from previous instance)" >> ~/.bashrc
    cat bashrc-additions.txt >> ~/.bashrc
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
            clone_path="~/projects/$repo_name"
            
            echo "Cloning $repo_name from $remote_url..."
            if git clone "$remote_url" "$HOME/projects/$repo_name"; then
                cd "$HOME/projects/$repo_name"
                
                # Switch to the original branch if it's not main/master
                if [ "$current_branch" != "main" ] && [ "$current_branch" != "master" ] && [ "$current_branch" != "unknown" ]; then
                    git checkout "$current_branch" 2>/dev/null || echo "Could not switch to branch $current_branch"
                fi
                
                echo "Successfully cloned $repo_name to ~/projects/$repo_name"
                
                # If there were uncommitted changes, show the file
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

echo "=== Setup Complete ==="
echo "Finished at: $(date)"
echo ""
echo "Next steps:"
echo "1. Activate virtual environment: source ~/aws-env/bin/activate"
echo "2. Source updated bashrc: source ~/.bashrc"
echo "3. Verify setup: python --version && pip list"
echo ""
echo "Don't forget to:"
echo "- Update your SSH keys for Git access"
echo "- Configure AWS credentials if needed"
echo "- Update security groups to match your previous instance"
echo "- Check cloned repositories in ~/projects/"
echo "- Review any uncommitted changes files (git-changes-*.txt)"
SCRIPT_EOF

chmod +x setup-new-instance.sh

echo
echo "=== Capture Complete ==="
echo "Files created in ~/setup-capture/:"
ls -la ~/setup-capture/
echo
echo "Copy the entire ~/setup-capture/ directory to your new instance and run:"
echo "cd ~/setup-capture && ./setup-new-instance.sh"