import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib
import os

class SettingsDialog(Adw.PreferencesWindow):
    def __init__(self, parent, **kwargs):
        super().__init__(**kwargs)
        self.set_transient_for(parent)
        self.set_title("Settings")
        self.set_search_enabled(False)  # Hide search bar
        
        page = Adw.PreferencesPage()
        self.add(page)
        
        group = Adw.PreferencesGroup(title="General")
        page.add(group)
        
        # Autostart
        self.autostart_row = Adw.SwitchRow(title="Launch on Boot")
        self.autostart_row.set_subtitle("Start application automatically in the background")
        self.autostart_row.set_active(self.check_autostart())
        self.autostart_row.connect("notify::active", self.on_autostart_changed)
        group.add(self.autostart_row)
        
        # Auto-mount
        # This global switch enables/disables the feature entirely. 
        # Fine-grained control could be per-vault, but global is a good start.
        self.automount_row = Adw.SwitchRow(title="Auto-mount Vaults")
        self.automount_row.set_subtitle("Attempt to unlock saved vaults on startup")
        
        # Use JSON file for settings (no GSettings schema compiled)
        self.settings_file = os.path.join(GLib.get_user_config_dir(), "locker", "settings.json")
        self.load_settings()
        
        self.automount_row.connect("notify::active", self.on_automount_changed)
        group.add(self.automount_row)

    def get_host_autostart_dir(self):
        # In Flatpak, os.path.expanduser("~") points to sandbox home.
        # with filesystem=host, we can access real home but need path.
        # Assuming modern Linux (Silverblue/Fedora uses /var/home)
        import getpass
        user = getpass.getuser()
        # Try /var/home first (common on atomic), then /home
        paths = [f"/var/home/{user}/.config/autostart", f"/home/{user}/.config/autostart"]
        for p in paths:
            if os.path.exists(os.path.dirname(p)): # Check if .config exists parent
                 return p
        return paths[0] # Default fallthrough

    def check_autostart(self):
        autostart_dir = self.get_host_autostart_dir()
        path = os.path.join(autostart_dir, "io.github.ljam96.cryptomatorgtk.desktop")
        return os.path.exists(path)

    def on_autostart_changed(self, row, param):
        is_active = row.get_active()
        autostart_dir = self.get_host_autostart_dir()
        autostart_path = os.path.join(autostart_dir, "io.github.ljam96.cryptomatorgtk.desktop")
        
        if is_active:
            os.makedirs(autostart_dir, exist_ok=True)
            # Create desktop entry
            # Note: Exec needs to be valid on HOST. 'flatpak run ...' is correct.
            content = """[Desktop Entry]
Type=Application
Name=Cryptomator GTK
Exec=flatpak run io.github.ljam96.cryptomatorgtk --background
Icon=io.github.ljam96.cryptomatorgtk
X-Flatpak=io.github.ljam96.cryptomatorgtk
Terminal=false
Categories=Utility;Security;
"""
            try:
                with open(autostart_path, 'w') as f:
                    f.write(content)
            except Exception as e:
                print(f"Failed to enable autostart: {e}")
                # row.set_active(False) 
        else:
            if os.path.exists(autostart_path):
                try:
                    os.remove(autostart_path)
                except Exception as e:
                    print(f"Failed to disable autostart: {e}")

    def load_settings(self):
        import json
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                    self.automount_row.set_active(data.get("automount", False))
            except:
                pass

    def on_automount_changed(self, row, param):
        import json
        data = {}
        if os.path.exists(self.settings_file):
             try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
             except: pass
        
        data["automount"] = row.get_active()
        
        os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
        with open(self.settings_file, 'w') as f:
            json.dump(data, f)
