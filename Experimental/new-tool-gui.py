#!/usr/bin/env python3
"""
UHF RFID Reader/Writer GUI
Simple graphical interface for tag operations
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
from uhf_rfid_tool import URFIDReader, MemoryBank, LockTarget, LockAction


class RFIDReaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("UHF RFID Reader/Writer")
        self.root.geometry("800x700")
        
        self.reader = None
        self.current_tags = []
        
        self._create_widgets()
        
    def _create_widgets(self):
        # Connection Frame
        conn_frame = ttk.LabelFrame(self.root, text="Connection", padding=10)
        conn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(conn_frame, text="COM Port:").grid(row=0, column=0, sticky=tk.W)
        self.port_var = tk.StringVar(value="COM3")
        ttk.Entry(conn_frame, textvariable=self.port_var, width=10).grid(row=0, column=1, padx=5)
        
        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=2, padx=5)
        
        self.status_label = ttk.Label(conn_frame, text="Not Connected", foreground="red")
        self.status_label.grid(row=0, column=3, padx=10)
        
        # Tag Selection Frame
        tag_frame = ttk.LabelFrame(self.root, text="Tag Selection", padding=10)
        tag_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(tag_frame, text="Scan Tags", command=self.scan_tags).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(tag_frame, text="Selected Tag:").pack(side=tk.LEFT, padx=5)
        self.tag_var = tk.StringVar()
        self.tag_combo = ttk.Combobox(tag_frame, textvariable=self.tag_var, width=30, state='readonly')
        self.tag_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Operations Notebook
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Read Tab
        read_frame = ttk.Frame(notebook, padding=10)
        notebook.add(read_frame, text="Read")
        
        ttk.Button(read_frame, text="Read TID", command=self.read_tid, width=20).pack(pady=5)
        ttk.Button(read_frame, text="Read EPC", command=self.read_epc, width=20).pack(pady=5)
        ttk.Button(read_frame, text="Read Reserved (Passwords)", command=self.read_reserved, width=20).pack(pady=5)
        ttk.Button(read_frame, text="Read User Memory", command=self.read_user, width=20).pack(pady=5)
        ttk.Button(read_frame, text="Read All", command=self.read_all, width=20).pack(pady=5)
        
        # Write Tab
        write_frame = ttk.Frame(notebook, padding=10)
        notebook.add(write_frame, text="Write")
        
        # Write EPC
        epc_frame = ttk.LabelFrame(write_frame, text="Write EPC", padding=10)
        epc_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(epc_frame, text="New EPC (hex):").grid(row=0, column=0, sticky=tk.W)
        self.new_epc_var = tk.StringVar()
        ttk.Entry(epc_frame, textvariable=self.new_epc_var, width=30).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(epc_frame, text="(Will be padded to 96 bits)", foreground="gray").grid(row=1, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(epc_frame, text="Access Password:").grid(row=2, column=0, sticky=tk.W)
        self.epc_pwd_var = tk.StringVar(value="00000000")
        ttk.Entry(epc_frame, textvariable=self.epc_pwd_var, width=30).grid(row=2, column=1, padx=5, pady=2)
        
        ttk.Button(epc_frame, text="Write EPC", command=self.write_epc).grid(row=3, column=0, columnspan=2, pady=5)
        
        # Write Passwords
        pwd_frame = ttk.LabelFrame(write_frame, text="Write Passwords", padding=10)
        pwd_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(pwd_frame, text="Kill Password:").grid(row=0, column=0, sticky=tk.W)
        self.kill_pwd_var = tk.StringVar()
        ttk.Entry(pwd_frame, textvariable=self.kill_pwd_var, width=30).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(pwd_frame, text="Access Password:").grid(row=1, column=0, sticky=tk.W)
        self.access_pwd_var = tk.StringVar()
        ttk.Entry(pwd_frame, textvariable=self.access_pwd_var, width=30).grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(pwd_frame, text="Current Access Pwd:").grid(row=2, column=0, sticky=tk.W)
        self.current_pwd_var = tk.StringVar(value="00000000")
        ttk.Entry(pwd_frame, textvariable=self.current_pwd_var, width=30).grid(row=2, column=1, padx=5, pady=2)
        
        ttk.Button(pwd_frame, text="Write Passwords", command=self.write_passwords).grid(row=3, column=0, columnspan=2, pady=5)
        
        # Lock Tab
        lock_frame = ttk.Frame(notebook, padding=10)
        notebook.add(lock_frame, text="Lock")
        
        ttk.Label(lock_frame, text="Lock Target:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.lock_target_var = tk.StringVar(value="EPC_MEMORY")
        targets = ttk.Combobox(lock_frame, textvariable=self.lock_target_var, width=25, state='readonly')
        targets['values'] = ['KILL_PASSWORD', 'ACCESS_PASSWORD', 'EPC_MEMORY', 'TID_MEMORY', 'USER_MEMORY']
        targets.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(lock_frame, text="Lock Action:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.lock_action_var = tk.StringVar(value="WRITABLE_SECURED")
        actions = ttk.Combobox(lock_frame, textvariable=self.lock_action_var, width=25, state='readonly')
        actions['values'] = ['WRITABLE_ANY', 'WRITABLE_PERMANENT', 'WRITABLE_SECURED', 'NEVER_WRITABLE']
        actions.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(lock_frame, text="Access Password:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.lock_pwd_var = tk.StringVar(value="00000000")
        ttk.Entry(lock_frame, textvariable=self.lock_pwd_var, width=26).grid(row=2, column=1, padx=5, pady=5)
        
        ttk.Button(lock_frame, text="Set Lock State", command=self.set_lock).grid(row=3, column=0, columnspan=2, pady=10)
        
        ttk.Label(lock_frame, text="⚠️ Warning: Permanent locks cannot be undone!", 
                 foreground="red").grid(row=4, column=0, columnspan=2, pady=10)
        
        # Log Frame
        log_frame = ttk.LabelFrame(self.root, text="Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Bottom buttons
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(bottom_frame, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Reader Info", command=self.get_reader_info).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Beep", command=self.beep).pack(side=tk.LEFT, padx=5)
    
    def log(self, message):
        """Add message to log"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update()
    
    def clear_log(self):
        """Clear log"""
        self.log_text.delete(1.0, tk.END)
    
    def toggle_connection(self):
        """Connect/disconnect from reader"""
        if self.reader and self.reader.serial and self.reader.serial.is_open:
            self.reader.disconnect()
            self.reader = None
            self.connect_btn.config(text="Connect")
            self.status_label.config(text="Not Connected", foreground="red")
            self.log("Disconnected")
        else:
            port = self.port_var.get()
            self.reader = URFIDReader(port)
            if self.reader.connect():
                self.connect_btn.config(text="Disconnect")
                self.status_label.config(text="Connected", foreground="green")
                self.log(f"Connected to {port}")
            else:
                self.reader = None
                self.log("Connection failed")
    
    def check_connection(self):
        """Check if reader is connected"""
        if not self.reader or not self.reader.serial or not self.reader.serial.is_open:
            messagebox.showerror("Error", "Not connected to reader")
            return False
        return True
    
    def scan_tags(self):
        """Scan for tags"""
        if not self.check_connection():
            return
        
        self.log("\n" + "="*50)
        self.log("Scanning for tags...")
        
        def scan():
            tags = self.reader.inventory()
            if tags:
                self.current_tags = tags
                self.tag_combo['values'] = tags
                self.tag_combo.current(0)
                self.log(f"Found {len(tags)} tag(s)")
            else:
                self.log("No tags found")
        
        threading.Thread(target=scan, daemon=True).start()
    
    def read_tid(self):
        """Read TID"""
        if not self.check_connection():
            return
        
        self.log("\n" + "="*50)
        
        def read():
            tid = self.reader.read_tid()
            if tid:
                self.log(f"TID: {tid}")
                if len(tid) >= 24:
                    self.log(f"  Manufacturer: 0x{tid[4:8]}")
                    self.log(f"  Model: 0x{tid[8:12]}")
                    self.log(f"  Serial: {tid[12:]}")
        
        threading.Thread(target=read, daemon=True).start()
    
    def read_epc(self):
        """Read EPC"""
        if not self.check_connection():
            return
        
        self.log("\n" + "="*50)
        
        def read():
            epc = self.reader.read_epc()
            if epc:
                self.log(f"EPC: {epc}")
        
        threading.Thread(target=read, daemon=True).start()
    
    def read_reserved(self):
        """Read Reserved memory"""
        if not self.check_connection():
            return
        
        self.log("\n" + "="*50)
        
        def read():
            reserved = self.reader.read_reserved()
            if reserved:
                self.log(f"Kill Password: {reserved['kill_password']}")
                self.log(f"Access Password: {reserved['access_password']}")
        
        threading.Thread(target=read, daemon=True).start()
    
    def read_user(self):
        """Read User memory"""
        if not self.check_connection():
            return
        
        self.log("\n" + "="*50)
        
        def read():
            user = self.reader.read_user(word_count=2)
            if user:
                self.log(f"User Memory: {user}")
        
        threading.Thread(target=read, daemon=True).start()
    
    def read_all(self):
        """Read all memory areas"""
        if not self.check_connection():
            return
        
        self.log("\n" + "="*50)
        self.log("Reading all memory areas...")
        
        def read():
            # TID
            tid = self.reader.read_tid()
            if tid:
                self.log(f"\nTID: {tid}")
                if len(tid) >= 24:
                    self.log(f"  Manufacturer: 0x{tid[4:8]}")
                    self.log(f"  Model: 0x{tid[8:12]}")
                    self.log(f"  Serial: {tid[12:]}")
            
            # EPC
            epc = self.reader.read_epc()
            if epc:
                self.log(f"\nEPC: {epc}")
            
            # Reserved
            reserved = self.reader.read_reserved()
            if reserved:
                self.log(f"\nKill Password: {reserved['kill_password']}")
                self.log(f"Access Password: {reserved['access_password']}")
            
            # User
            user = self.reader.read_user(word_count=2)
            if user:
                self.log(f"\nUser Memory: {user}")
        
        threading.Thread(target=read, daemon=True).start()
    
    def write_epc(self):
        """Write EPC"""
        if not self.check_connection():
            return
        
        new_epc = self.new_epc_var.get().strip()
        if not new_epc:
            messagebox.showerror("Error", "Enter new EPC value")
            return
        
        pwd = self.epc_pwd_var.get().strip()
        
        self.log("\n" + "="*50)
        
        def write():
            if self.reader.write_epc(new_epc, pwd):
                self.log("✓ EPC written successfully")
                messagebox.showinfo("Success", "EPC written successfully")
                # Refresh tag list
                time.sleep(0.5)
                self.scan_tags()
            else:
                self.log("✗ Failed to write EPC")
        
        threading.Thread(target=write, daemon=True).start()
    
    def write_passwords(self):
        """Write passwords"""
        if not self.check_connection():
            return
        
        # Get selected tag EPC
        epc = self.tag_var.get().strip()
        if not epc:
            messagebox.showerror("Error", "No tag selected. Scan for tags first.")
            return
        
        kill_pwd = self.kill_pwd_var.get().strip() or None
        access_pwd = self.access_pwd_var.get().strip() or None
        current_pwd = self.current_pwd_var.get().strip()
        
        if not kill_pwd and not access_pwd:
            messagebox.showerror("Error", "Enter at least one password to write")
            return
        
        self.log("\n" + "="*50)
        self.log(f"Target tag: {epc}")
        
        def write():
            if self.reader.write_password(kill_pwd, access_pwd, current_pwd, epc):
                self.log("✓ Passwords written successfully")
                messagebox.showinfo("Success", "Passwords written successfully")
            else:
                self.log("✗ Failed to write passwords")
        
        threading.Thread(target=write, daemon=True).start()
    
    def set_lock(self):
        """Set lock state"""
        if not self.check_connection():
            return
        
        # Get selected tag EPC
        epc = self.tag_var.get().strip()
        if not epc:
            messagebox.showerror("Error", "No tag selected. Scan for tags first.")
            return
        
        target_name = self.lock_target_var.get()
        action_name = self.lock_action_var.get()
        pwd = self.lock_pwd_var.get().strip()
        
        if pwd == "00000000":
            messagebox.showerror("Error", "Access password cannot be 00000000 for lock operations")
            return
        
        # Confirm permanent locks
        if "PERMANENT" in action_name or "NEVER" in action_name:
            if not messagebox.askyesno("Confirm", 
                                      f"This will PERMANENTLY lock {target_name}.\n"
                                      "This action CANNOT be undone!\n\n"
                                      "Are you sure?"):
                return
        
        target = getattr(LockTarget, target_name)
        action = getattr(LockAction, action_name)
        
        self.log("\n" + "="*50)
        self.log(f"Target tag: {epc}")
        
        def lock():
            if self.reader.lock_memory(target, action, pwd, epc):
                self.log(f"✓ Lock state set: {target_name} -> {action_name}")
                messagebox.showinfo("Success", "Lock state set successfully")
            else:
                self.log("✗ Failed to set lock state")
        
        threading.Thread(target=lock, daemon=True).start()
    
    def get_reader_info(self):
        """Get reader information"""
        if not self.check_connection():
            return
        
        self.log("\n" + "="*50)
        
        def info():
            info = self.reader.get_reader_info()
            if info:
                self.log(f"Version: {info['version']}")
                self.log(f"Type: {info['type']}")
                self.log(f"Protocols: {', '.join(info['protocols'])}")
                self.log(f"Power: {info['power']}")
                self.log(f"Scan Time: {info['scan_time']}")
        
        threading.Thread(target=info, daemon=True).start()
    
    def beep(self):
        """Make reader beep"""
        if not self.check_connection():
            return
        
        threading.Thread(target=lambda: self.reader.beep(times=1), daemon=True).start()


def main():
    root = tk.Tk()
    app = RFIDReaderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()