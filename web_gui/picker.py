import sys
import os
import platform

def pick(mode='input'):
    system = platform.system()
    
    # Try tkinter with transparent topmost window
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.attributes('-alpha', 0.0)
        root.attributes('-topmost', True)
        root.overrideredirect(True)
        root.geometry('1x1+0+0')
        root.lift()
        root.focus_force()
        root.update()
        
        if mode == 'input':
            path = filedialog.askopenfilename(
                parent=root,
                title="Select Script (DOCX)",
                filetypes=[("Word Documents (*.docx)", "*.docx"), ("All Files (*.*)", "*.*")]
            )
        else:
            path = filedialog.asksaveasfilename(
                parent=root,
                title="Save Prompts As",
                defaultextension=".docx",
                filetypes=[("Word Documents (*.docx)", "*.docx")]
            )
        root.destroy()
        if path:
            return path
    except Exception as e:
        pass

    # macOS AppleScript fallback
    if system == 'Darwin':
        import subprocess
        try:
            if mode == 'input':
                cmd = ['osascript', '-e', 'POSIX path of (choose file of type {"docx"} with prompt "Select Script")']
            else:
                cmd = ['osascript', '-e', 'POSIX path of (choose file name default name "prompts.docx" with prompt "Save Prompts As")']
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return res.stdout.strip()
        except Exception:
            pass

    return ""

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'input'
    result = pick(mode)
    if result:
        sys.stdout.write(result)
        sys.stdout.flush()
