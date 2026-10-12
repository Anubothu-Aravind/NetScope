#!/usr/bin/env bash
# ==============================================================================
# setup.sh - Portable Environment Provisioner for NetScope
# Supports macOS (Darwin), Ubuntu/Debian, Fedora/RHEL, Arch, and WSL.
# Checks and provisions Python 3, Node.js, venv, and dependencies cleanly.
# ==============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# Text Styling
BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}============================================================${NC}"
echo -e "${CYAN}${BOLD} NetScope Portable Environment Setup${NC}"
echo -e "${CYAN}${BOLD}============================================================${NC}"

# 1. Detect Operating System and Architecture
OS="$(uname -s)"
ARCH="$(uname -m)"
IS_WSL=false
if [ -f /proc/version ] && grep -qi "microsoft" /proc/version; then
  IS_WSL=true
fi

echo -e "[*] Platform: ${BOLD}${OS} (${ARCH})${NC} $([ "$IS_WSL" = true ] && echo "[WSL]")"

# Detect Package Manager
PKG_MGR=""
if command -v brew >/dev/null 2>&1; then
  PKG_MGR="brew"
elif command -v apt-get >/dev/null 2>&1; then
  PKG_MGR="apt"
elif command -v dnf >/dev/null 2>&1; then
  PKG_MGR="dnf"
elif command -v pacman >/dev/null 2>&1; then
  PKG_MGR="pacman"
fi

# 2. Check and Validate Python (>= 3.9)
echo -e "\n[1/6] Checking Python runtime..."
PYTHON_BIN=""
for candidate in python3 python python3.13 python3.12 python3.11 python3.10 python3.9; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY_VER="$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")"
    MAJOR="$(echo "$PY_VER" | cut -d. -f1)"
    MINOR="$(echo "$PY_VER" | cut -d. -f2)"
    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 9 ]; then
      PYTHON_BIN="$(command -v "$candidate")"
      echo -e "      Found compatible Python: ${GREEN}${PYTHON_BIN} (v${PY_VER})${NC}"
      break
    fi
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo -e "${RED}[ERROR] Python 3.9 or higher was not found on this system.${NC}"
  echo -e "Please install Python 3 using your package manager:"
  case "$PKG_MGR" in
    brew)   echo "  brew install python@3.11" ;;
    apt)    echo "  sudo apt update && sudo apt install -y python3 python3-venv python3-pip" ;;
    dnf)    echo "  sudo dnf install -y python3 python3-pip" ;;
    pacman) echo "  sudo pacman -S python python-pip" ;;
    *)      echo "  Visit https://www.python.org/downloads/ to install Python." ;;
  esac
  exit 1
fi

# 3. Check and Validate Node.js & npm (>= 18)
echo -e "\n[2/6] Checking Node.js and npm..."
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo -e "${YELLOW}[!] Node.js or npm is missing.${NC}"
  if [ "$PKG_MGR" = "brew" ]; then
    echo "      Attempting to install Node.js via Homebrew..."
    brew install node || true
  elif [ "$PKG_MGR" = "apt" ]; then
    echo "      To install Node.js 18+ on Debian/Ubuntu, run:"
    echo "      curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs"
  fi
fi

if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  NODE_VER="$(node -v | tr -d 'v')"
  NPM_VER="$(npm -v)"
  echo -e "      Node.js: ${GREEN}v${NODE_VER}${NC} | npm: ${GREEN}v${NPM_VER}${NC}"
else
  echo -e "${RED}[ERROR] Node.js and npm are required for the Desktop and Mobile frontends.${NC}"
  echo -e "Please install Node.js (version 18 or newer) from https://nodejs.org/"
  exit 1
fi

# 4. Setup Python Virtual Environment (.venv) & Requirements
echo -e "\n[3/6] Configuring Python virtual environment..."
if [ ! -d ".venv" ] || [ ! -f ".venv/bin/python" ]; then
  echo "      Creating virtual environment in .venv..."
  "$PYTHON_BIN" -m venv .venv
else
  echo "      Virtual environment already present in .venv."
fi

VENV_PY=".venv/bin/python"
VENV_PIP=".venv/bin/pip"

echo "      Upgrading pip and installing Python dependencies..."
"$VENV_PIP" install --quiet --upgrade pip
if [ -f "requirements.txt" ]; then
  "$VENV_PIP" install --quiet -r requirements.txt
  echo -e "      Python dependencies installed: ${GREEN}OK${NC}"
else
  echo -e "      ${YELLOW}WARNING: requirements.txt not found.${NC}"
fi

# 5. Install Frontend Dependencies
echo -e "\n[4/6] Installing frontend dependencies..."
if [ -d "frontend/desktop" ]; then
  echo "      Installing Desktop frontend dependencies (frontend/desktop)..."
  npm --prefix frontend/desktop install --no-audit --no-fund --quiet
  echo -e "      Desktop dependencies: ${GREEN}OK${NC}"
fi

if [ -d "frontend/mobile" ]; then
  echo "      Installing Mobile frontend dependencies (frontend/mobile)..."
  npm --prefix frontend/mobile install --no-audit --no-fund --quiet
  echo -e "      Mobile dependencies: ${GREEN}OK${NC}"
fi

# 6. Test Data Files Generation
echo -e "\n[5/6] Ensuring test payload files exist..."
mkdir -p tests/data
if [ ! -f "tests/data/test_1mb.bin" ]; then
  echo "      Creating 1 MB test payload (tests/data/test_1mb.bin)..."
  dd if=/dev/urandom of=tests/data/test_1mb.bin bs=1048576 count=1 status=none 2>/dev/null || dd if=/dev/urandom of=tests/data/test_1mb.bin bs=1M count=1 status=none
fi

if [ ! -f "tests/data/test_10mb.bin" ]; then
  echo "      Creating 10 MB test payload (tests/data/test_10mb.bin)..."
  dd if=/dev/urandom of=tests/data/test_10mb.bin bs=1048576 count=10 status=none 2>/dev/null || dd if=/dev/urandom of=tests/data/test_10mb.bin bs=1M count=10 status=none
fi
echo -e "      Test data files: ${GREEN}OK${NC}"

# 7. Operating System Specific Network Testbed Configuration
echo -e "\n[6/6] Checking network emulation capabilities..."
if [ "$OS" = "Darwin" ]; then
  echo -e "      macOS detected: NetScope runs in ${GREEN}Standalone Software Impairment Mode${NC}."
  echo "      Real-time delay pacing, loss emulation, RTO retransmissions, and packet capture"
  echo "      run locally over loopback without requiring Linux kernel namespaces."
elif [ "$OS" = "Linux" ]; then
  if command -v ip >/dev/null 2>&1 && [ -f "network/install_sudoers.sh" ]; then
    echo "      Linux kernel detected. Testing sudo access for network namespaces..."
    if sudo -n true 2>/dev/null; then
      echo "      Configuring passwordless testbed rules..."
      sudo bash network/install_sudoers.sh 2>/dev/null || true
      if [ -f "/opt/netscope/netns_setup.sh" ]; then
        sudo -n /opt/netscope/netns_setup.sh up 2>/dev/null || true
      fi
    else
      echo -e "      ${YELLOW}Notice: Sudo password required for Linux network namespaces.${NC}"
      echo "      Run 'sudo bash network/install_sudoers.sh' if you wish to use netem namespaces."
      echo "      Otherwise, NetScope will operate in standalone loopback mode seamlessly."
    fi
  else
    echo "      Linux standalone mode active."
  fi
fi

# Verification Check
echo -e "\n[*] Verifying installation..."
"$VENV_PY" -c "import fastapi, uvicorn, cryptography; print('      Backend modules verified: OK')"
echo -e "      Setup verification: ${GREEN}SUCCESSFUL${NC}"

echo -e "\n${GREEN}${BOLD}============================================================${NC}"
echo -e "${GREEN}${BOLD} NetScope Setup Complete!${NC}"
echo -e "${GREEN}${BOLD}============================================================${NC}"
echo -e "To launch all NetScope services automatically, run:"
echo -e "  ${CYAN}${BOLD}./run.sh${NC}"
echo ""
echo -e "Or run individual services manually:"
echo -e "  ${BOLD}Backend:${NC}    .venv/bin/uvicorn app.main:app --port 8000"
echo -e "  ${BOLD}TCP Server:${NC} .venv/bin/python server/tcp_server.py"
echo -e "  ${BOLD}Desktop UI:${NC} npm --prefix frontend/desktop run dev"
echo -e "  ${BOLD}Mobile UI:${NC}  npm --prefix frontend/mobile run dev"
echo ""
