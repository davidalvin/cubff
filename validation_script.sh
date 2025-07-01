#!/bin/bash

# Validation script that runs as test user
echo "=== Validation Results ==="
echo "User: $(whoami)"
echo "Home: $HOME"
echo "Date: $(date)"
echo

# Check Python
echo "Python version: $(python3 --version 2>/dev/null || echo 'NOT FOUND')"

# Check virtual environment
if [ -d ~/aws-env ]; then
    echo "Virtual environment: EXISTS"
    source ~/aws-env/bin/activate
    echo "Virtual env Python: $(python --version 2>/dev/null || echo 'FAILED')"
    echo "Pip packages installed: $(pip list 2>/dev/null | wc -l || echo '0')"
    
    # Check key packages
    echo "Key packages:"
    for pkg in boto3 awscli requests flask django; do
        if pip show "$pkg" >/dev/null 2>&1; then
            version=$(pip show "$pkg" | grep Version: | cut -d' ' -f2)
            echo "  $pkg: $version"
        else
            echo "  $pkg: NOT INSTALLED"
        fi
    done
    deactivate
else
    echo "Virtual environment: MISSING"
fi

# Check configuration files
echo
echo "Configuration files:"
echo "  .gitconfig: $([ -f ~/.gitconfig ] && echo 'EXISTS' || echo 'MISSING')"
echo "  .vimrc: $([ -f ~/.vimrc ] && echo 'EXISTS' || echo 'MISSING')"
echo "  .ssh/config: $([ -f ~/.ssh/config ] && echo 'EXISTS' || echo 'MISSING')"

# Check bashrc customizations
if tail -10 ~/.bashrc | grep -q 'Custom additions'; then
    echo "  bashrc customizations: APPLIED"
else
    echo "  bashrc customizations: NOT APPLIED"
fi

# Check projects directory
if [ -d ~/projects ]; then
    repo_count=$(ls ~/projects 2>/dev/null | wc -l)
    echo "  projects directory: EXISTS ($repo_count repositories)"
else
    echo "  projects directory: MISSING"
fi

# Check swap
echo
echo "Swap status:"
swapon --show 2>/dev/null | grep -q swap && echo "  Swap: ACTIVE" || echo "  Swap: INACTIVE"

echo
echo "=== Validation Complete ==="
