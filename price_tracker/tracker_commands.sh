# ════════════════════════════════════════════════════════════════
# 1. CORE COMMANDS (Daily Use)
# ════════════════════════════════════════════════════════════════
status() {
  sudo systemctl status amazon-price-tracker
}
alias st=status

logs() {
  journalctl -u amazon-price-tracker -f
}
alias lg=logs

state() {
  cat ~/robust-price-tracker/amazon_state.json
}
alias stt=state

test-tg() {
  cd ~/robust-price-tracker && python3 -c "
import asyncio
from telegram import Bot
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
async def t(): await Bot(TELEGRAM_TOKEN).send_message(TELEGRAM_CHAT_ID, '🟢 TEST OK')
asyncio.run(t())
"
}
alias tg=test-tg

# ════════════════════════════════════════════════════════════════
# 2. DEPLOY/REDEPLOY (Full Reset)
# ════════════════════════════════════════════════════════════════
deploy() {
  cd ~/robust-price-tracker
  sudo systemctl stop amazon-price-tracker
  git pull origin main  # If using git
  pip install -r requirements.txt  # If exists
  sudo systemctl start amazon-price-tracker
  echo "✅ Deployed $(date)"
}
alias deploy=deploy

redeploy() {
  deploy && sleep 5 && st && lg
}

# ════════════════════════════════════════════════════════════════
# 3. TROUBLESHOOTING
# ════════════════════════════════════════════════════════════════
restart() {
  sudo systemctl restart amazon-price-tracker && sleep 3 && st
}

stop() {
  sudo systemctl stop amazon-price-tracker
}

logs-tail() {
  journalctl -u amazon-price-tracker -n 50 | tail -20
}

cpu() {
  sudo systemctl status amazon-price-tracker | grep CPU
}

# ════════════════════════════════════════════════════════════════
# 4. MANUAL TESTING (No Service)
# ════════════════════════════════════════════════════════════════
manual-run() {
  cd ~/robust-price-tracker && python3 amazon_price_tracker.py
}

dry-run() {
  cd ~/robust-price-tracker && timeout 60s python3 amazon_price_tracker.py
}

# ════════════════════════════════════════════════════════════════
# 5. CLEANUP/RESET
# ════════════════════════════════════════════════════════════════
reset-state() {
  rm -f ~/robust-price-tracker/amazon_state.json && echo "🗑️ State reset"
}

full-reset() {
  sudo systemctl stop amazon-price-tracker
  rm -f ~/robust-price-tracker/amazon_state.json
  sudo systemctl start amazon-price-tracker
  echo "🔄 Full reset $(date)"
}

# ════════════════════════════════════════════════════════════════
# 6. QUICK STATUS DASHBOARD
# ════════════════════════════════════════════════════════════════
dashboard() {
  echo "=== Amazon Tracker Status ==="
  sudo systemctl status amazon-price-tracker --no-pager -l | head -20
  echo ""
  echo "=== State Snapshot ==="
  ls -lh ~/robust-price-tracker/*state*.json 2>/dev/null || echo "No state"
  echo ""
  echo "=== Last 3 Logs ==="
  journalctl -u amazon-price-tracker -n 3 -o short-iso
}
alias dash=dashboard

# ════════════════════════════════════════════════════════════════
# USAGE EXAMPLES:
# st          # Status
# lg          # Live logs
# tg          # Test Telegram
# stt         # Show prices
# redeploy    # Git pull + restart
# dash        # All-in-one status
# full-reset  # Nuke + restart
# ════════════════════════════════════════════════════════════════
