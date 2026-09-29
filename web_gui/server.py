"""
Prompt Generator — Flask Backend
Serves the web UI and bridges it to the Antigravity CLI Python logic.
"""

import os
import sys
import json
import logging
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
import threading
import re
import platform
import subprocess

# Setup root and paths (supports PyInstaller frozen executable and dev mode)
if getattr(sys, 'frozen', False):
    _REPO_ROOT = Path(sys._MEIPASS)
else:
    _REPO_ROOT = Path(__file__).resolve().parent.parent

_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

_WEB_GUI_DIR = _REPO_ROOT / "web_gui"

from prompt_generator.gui_account_manager import AccountManager, fetch_quota
from prompt_generator.gui_worker import GenerationWorker

app = Flask(__name__, static_folder=str(_WEB_GUI_DIR), static_url_path='')
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

account_manager = AccountManager()
active_worker = None

# ==========================================
# Frontend Routes
# ==========================================

@app.route('/')
def index():
    return send_from_directory(str(_WEB_GUI_DIR), 'index.html')

# ==========================================
# Account & Quota API
# ==========================================

@app.route('/api/account')
def get_account():
    hint = account_manager.get_current_email_hint()
    active = account_manager.get_active_account()
    label = active.label if active else hint
    return jsonify({"label": label})

@app.route('/api/quota')
def get_quota():
    info = fetch_quota()
    return jsonify({
        "gemini_pct": info.overall_gemini_pct(),
        "claude_pct": info.claude_weekly_pct,
        "error": info.error
    })

@app.route('/api/accounts')
def list_accounts():
    accounts = account_manager.list_accounts()
    return jsonify([a.to_dict() for a in accounts])

@app.route('/api/accounts/switch', methods=['POST'])
def switch_account():
    data = request.json
    name = data.get('name')
    success = account_manager.switch_account(name)
    if success:
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Failed to switch"}), 400

@app.route('/api/accounts/<name>', methods=['DELETE'])
def delete_account(name):
    account_manager.delete_account(name)
    return jsonify({"success": True})

@app.route('/api/accounts/save', methods=['POST'])
def save_account():
    data = request.json
    label = data.get('label', '').strip()
    if not label:
        return jsonify({"success": False, "error": "Label required"}), 400
    
    name = re.sub(r"[^a-zA-Z0-9_.-]", "_", label)[:40]
    try:
        account_manager.save_current_as_account(name, label)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/accounts/login', methods=['POST'])
def login():
    account_manager.launch_login_terminal()
    return jsonify({"success": True})

# ==========================================
# File Picker API (Native OS: Windows & macOS)
# ==========================================

@app.route('/api/browse')
def browse():
    req_type = request.args.get('type', 'input')
    import sys, subprocess
    
    picker_script = _REPO_ROOT / "web_gui" / "picker.py"
    selected_path = ""
    try:
        res = subprocess.run(
            [sys.executable, str(picker_script), req_type],
            capture_output=True,
            text=True,
            timeout=120
        )
        selected_path = res.stdout.strip()
    except Exception as e:
        print(f"[BROWSE] Error launching picker: {e}")
        selected_path = ""

    return jsonify({"path": selected_path})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400
        
    upload_dir = Path.cwd() / "uploads"
    upload_dir.mkdir(exist_ok=True)
    
    save_path = upload_dir / file.filename
    file.save(str(save_path))
    return jsonify({"success": True, "path": str(save_path.resolve())})



# ==========================================
# Generation API
# ==========================================

@app.route('/api/check_resume', methods=['POST'])
def check_resume():
    data = request.json
    path_str = data.get('input_path', '').strip()
    if not path_str:
        return jsonify({"resumable": False})
        
    p = Path(path_str)
    if not p.exists():
        return jsonify({"resumable": False})
        
    try:
        from prompt_generator.queue import BatchQueue
        from prompt_generator.config import PromptGeneratorConfig
        from prompt_generator.providers.antigravity_cli import AntigravityCLIProvider
        
        cfg_path = _REPO_ROOT / "config" / "prompt_generator_config.json"
        cfg = PromptGeneratorConfig.load(cfg_path, base_dir=_REPO_ROOT)
        prov = AntigravityCLIProvider(cfg)
        bq = BatchQueue(cfg, prov, cache_dir=Path.cwd() / ".prompt_gen_cache")
        
        job_id = bq.find_resumable_job(p)
        if job_id:
            job = bq.restore_job_from_cache(job_id)
            if job:
                return jsonify({
                    "resumable": True,
                    "job_id": job_id,
                    "completed": job.completed_scenes,
                    "total": job.total_scenes
                })
    except Exception:
        pass
        
    return jsonify({"resumable": False})

@app.route('/api/generate/start', methods=['POST'])
def start_generation():
    global active_worker
    
    if active_worker and active_worker.is_running:
        return jsonify({"error": "A generation is already running"}), 400
        
    data = request.json
    input_path = Path(data.get('input_path', ''))
    output_path = Path(data.get('output_path', ''))
    
    if not input_path.exists():
        return jsonify({"error": "Input file not found"}), 400
        
    active_worker = GenerationWorker(input_path, output_path, _REPO_ROOT)
    active_worker.start()
    
    return jsonify({"success": True})

@app.route('/api/generate/stop', methods=['POST'])
def stop_generation():
    global active_worker
    if active_worker and active_worker.is_running:
        active_worker.cancel()
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Not running"})

@app.route('/api/generate/poll')
def poll_generation():
    global active_worker
    if not active_worker:
        return jsonify({"is_running": False, "events": []})
        
    events = []
    while not active_worker.event_queue.empty():
        try:
            ev = active_worker.event_queue.get_nowait()
            payload = ev.payload
            
            # Serialize dataclass payloads to dict
            if hasattr(payload, '__dict__'):
                payload = payload.__dict__
            elif hasattr(payload, 'value'): # Enum
                payload = payload.value
                
            events.append({
                "type": ev.type.value if hasattr(ev.type, 'value') else ev.type,
                "payload": payload
            })
        except Exception:
            break
            
    return jsonify({
        "is_running": active_worker.is_running,
        "events": events
    })

@app.route('/api/open_file', methods=['POST'])
def open_file():
    data = request.json or {}
    path = data.get('path', '')
    if path and os.path.exists(path):
        system = platform.system()
        try:
            if system == 'Windows':
                os.startfile(path)
            elif system == 'Darwin':
                subprocess.run(['open', path], check=False)
            else:
                subprocess.run(['xdg-open', path], check=False)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": False, "error": "File not found"}), 400

# ==========================================
# Start Server
# ==========================================

if __name__ == '__main__':
    print("Starting Prompt Generator Web Server on http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000)
