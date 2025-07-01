#!/bin/bash

# Complete testing script for EC2 capture and restore process
# Run this as your main user (ubuntu/ec2-user)

set -e

TEST_USER="ec2test"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="test_log_${TIMESTAMP}.txt"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

log_step() {
    log "${BLUE}=== $1 ===${NC}"
}

log_success() {
    log "${GREEN}✓ $1${NC}"
}

log_warning() {
    log "${YELLOW}⚠ $1${NC}"
}

log_error() {
    log "${RED}✗ $1${NC}"
}

cleanup() {
    if [ "$1" = "EXIT" ]; then
        log_step "Cleaning up on exit..."
        if id "$TEST_USER" &>/dev/null; then
            log "Removing test user $TEST_USER..."
            sudo userdel -r "$TEST_USER" 2>/dev/null || log_warning "Could not remove user $TEST_USER"
        fi
    fi
}

# Set up cleanup on exit
trap 'cleanup EXIT' EXIT

log_step "EC2 Capture Script Test Suite - Started at $(date)"
log "Log file: $LOG_FILE"
log "Test user: $TEST_USER"
echo

# Step 1: Verify prerequisites
log_step "Step 1: Checking Prerequisites"

if [ ! -f "./capture-setup.sh" ]; then
    log_error "capture-setup.sh not found in current directory"
    log "Please ensure the capture script is in: $SCRIPT_DIR"
    exit 1
fi
log_success "Found capture-setup.sh"

if [ "$EUID" -eq 0 ]; then
    log_error "Don't run this as root - run as your normal user"
    exit 1
fi
log_success "Running as non-root user: $(whoami)"

# Check if test user already exists
if id "$TEST_USER" &>/dev/null; then
    log_warning "Test user $TEST_USER already exists - removing first"
    sudo userdel -r "$TEST_USER" 2>/dev/null || true
    sleep 2
fi

# Step 2: Run capture script
log_step "Step 2: Running Capture Script"
log "Executing: ./capture-setup.sh"

if ./capture-setup.sh > capture_output.log 2>&1; then
    log_success "Capture script completed successfully"
else
    log_error "Capture script failed"
    log "Last 10 lines of capture output:"
    tail -10 capture_output.log | sed 's/^/  /'
    exit 1
fi

# Verify capture output
if [ ! -d ~/setup-capture ]; then
    log_error "No setup-capture directory created"
    exit 1
fi

log "Capture files created:"
ls -la ~/setup-capture/ | sed 's/^/  /'

# Step 3: Create test user
log_step "Step 3: Creating Test User"

if sudo useradd -m -s /bin/bash "$TEST_USER"; then
    log_success "Created user $TEST_USER"
else
    log_error "Failed to create user $TEST_USER"
    exit 1
fi

# Give sudo privileges
sudo usermod -aG sudo "$TEST_USER"
echo "$TEST_USER:testpass123" | sudo chpasswd
log_success "Set password and sudo privileges for $TEST_USER"

# Step 4: Copy setup files
log_step "Step 4: Copying Setup Files to Test User"

sudo cp -r ~/setup-capture "/home/$TEST_USER/"
sudo chown -R "$TEST_USER:$TEST_USER" "/home/$TEST_USER/setup-capture"
log_success "Copied setup files to /home/$TEST_USER/setup-capture"

# Create test validation script
cat > validation_script.sh << 'VALIDATION_EOF'
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
VALIDATION_EOF

sudo cp validation_script.sh "/home/$TEST_USER/setup-capture/"
sudo chown "$TEST_USER:$TEST_USER" "/home/$TEST_USER/setup-capture/validation_script.sh"
sudo chmod +x "/home/$TEST_USER/setup-capture/validation_script.sh"

# Step 5: Run setup script as test user
log_step "Step 5: Running Setup Script as Test User"

# Create a script that switches to test user and runs setup
cat > run_as_test_user.sh << RUN_EOF
#!/bin/bash
cd /home/$TEST_USER/setup-capture
export DEBIAN_FRONTEND=noninteractive
./setup-new-instance.sh
RUN_EOF

chmod +x run_as_test_user.sh
sudo cp run_as_test_user.sh "/home/$TEST_USER/"
sudo chown "$TEST_USER:$TEST_USER" "/home/$TEST_USER/run_as_test_user.sh"

log "Running setup script as $TEST_USER (this may take several minutes)..."

if sudo -u "$TEST_USER" bash -c "cd /home/$TEST_USER && ./run_as_test_user.sh" > setup_output.log 2>&1; then
    log_success "Setup script completed successfully"
else
    log_error "Setup script failed"
    log "Last 20 lines of setup output:"
    tail -20 setup_output.log | sed 's/^/  /'
    log_warning "Continuing with validation to see partial results..."
fi

# Step 6: Run validation
log_step "Step 6: Running Validation"

if sudo -u "$TEST_USER" bash -c "cd /home/$TEST_USER/setup-capture && ./validation_script.sh" > validation_output.log 2>&1; then
    log_success "Validation completed"
    log "Validation results:"
    cat validation_output.log | sed 's/^/  /'
else
    log_error "Validation failed"
    cat validation_output.log | sed 's/^/  /'
fi

# Step 7: Summary and recommendations
log_step "Step 7: Test Summary"

# Analyze results
python3 << 'PYTHON_EOF'
import re
import sys

try:
    with open('validation_output.log', 'r') as f:
        content = f.read()
    
    print("=== Test Results Analysis ===")
    
    # Check key components
    checks = {
        'Virtual Environment': 'Virtual environment: EXISTS' in content,
        'Python Working': 'Virtual env Python:' in content and 'FAILED' not in content,
        'Packages Installed': 'Pip packages installed:' in content and 'Pip packages installed: 0' not in content,
        'AWS Packages': 'boto3:' in content and 'awscli:' in content,
        'Config Restored': '.gitconfig: EXISTS' in content,
        'Bashrc Updated': 'bashrc customizations: APPLIED' in content,
    }
    
    passed = sum(checks.values())
    total = len(checks)
    
    for check, result in checks.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {check}: {status}")
    
    print(f"\nOverall: {passed}/{total} checks passed")
    
    if passed >= total * 0.8:
        print("🎉 Test largely successful!")
        if passed < total:
            print("   Minor issues found - check details above")
    elif passed >= total * 0.5:
        print("⚠️  Partial success - some major issues")
    else:
        print("❌ Test failed - significant issues found")
        
except Exception as e:
    print(f"Could not analyze results: {e}")
PYTHON_EOF

log
log_success "Test completed! Check the following files for details:"
log "  - $LOG_FILE (this log)"
log "  - capture_output.log (capture script output)"
log "  - setup_output.log (setup script output)"  
log "  - validation_output.log (validation results)"

# Ask user if they want to keep the test user
echo
read -p "Keep test user '$TEST_USER' for manual inspection? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log "Removing test user $TEST_USER..."
    sudo userdel -r "$TEST_USER" 2>/dev/null || log_warning "Could not remove test user"
    log_success "Test user removed"
else
    log_warning "Test user $TEST_USER kept for manual inspection"
    log "To manually check: sudo su - $TEST_USER"
    log "To remove later: sudo userdel -r $TEST_USER"
    # Don't run cleanup on exit if user wants to keep
    trap - EXIT
fi

log_step "Test Suite Complete"