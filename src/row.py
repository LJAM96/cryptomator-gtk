import os
import threading
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GObject, Gio, GLib, Gdk
from vault import Vault, VaultStatus
from backend import CryptomatorBackend

class VaultRow(Adw.ActionRow):
    __gtype_name__ = 'VaultRow'

    def __init__(self, vault: Vault, **kwargs):
        super().__init__(**kwargs)
        self.vault = vault
        
        self.set_title(vault.name)
        self.set_subtitle(vault.path)
        
        # Status icon
        self.status_icon = Gtk.Image()
        self.add_prefix(self.status_icon)
        
        # Action buttons box
        self.suffix_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.add_suffix(self.suffix_box)

        # Open Folder button (shown only when unlocked)
        self.reveal_btn = Gtk.Button(icon_name="folder-open-symbolic")
        self.reveal_btn.set_tooltip_text("Open in Files")
        self.reveal_btn.add_css_class("flat")
        self.reveal_btn.connect("clicked", self.on_reveal_clicked)
        self.suffix_box.append(self.reveal_btn)

        # Unlock/Lock button
        self.action_btn = Gtk.Button()
        self.action_btn.add_css_class("flat")
        self.action_btn.connect("clicked", self.on_action_clicked)
        self.suffix_box.append(self.action_btn)
        
        # Connect activation
        self.set_activatable(False)
        
        self.setup_context_menu()
        self.update_status()

    def setup_context_menu(self):
        # Action group for the row
        action_group = Gio.SimpleActionGroup.new()
        
        # Remove action
        action = Gio.SimpleAction.new("remove", None)
        action.connect("activate", self.on_remove_action)
        action_group.add_action(action)
        
        # Rename action
        action = Gio.SimpleAction.new("rename", None)
        action.connect("activate", self.on_rename_action)
        action_group.add_action(action)
        
        self.insert_action_group("row", action_group)
        
        # Menu model
        menu = Gio.Menu()
        menu.append("Rename", "row.rename")
        menu.append("Remove", "row.remove")
        
        # Popover
        self.popover = Gtk.PopoverMenu.new_from_model(menu)
        self.popover.set_parent(self)
        self.popover.set_has_arrow(False)
        
        # Right click gesture
        gesture = Gtk.GestureClick.new()
        gesture.set_button(3) # Right click
        gesture.connect("released", self.on_secondary_click_released)
        self.add_controller(gesture)

    def on_secondary_click_released(self, gesture, n_press, x, y):
        # Position the popover at the click coordinates
        rect = Gdk.Rectangle()
        rect.x = x
        rect.y = y
        rect.width = 1
        rect.height = 1
        self.popover.set_pointing_to(rect)
        self.popover.popup()

    def on_remove_action(self, action, param):
        """Remove vault from the list"""
        dialog = Adw.MessageDialog(
            heading="Remove Vault",
            body=f"Remove '{self.vault.name}' from the vault list?\n\nThis will NOT delete the vault files, only remove it from this application.",
            transient_for=self.get_root()
        )
        
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Remove")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        
        def response_cb(dlg, response):
            if response == "remove":
                win = self.get_root()
                if hasattr(win, 'remove_vault'):
                    win.remove_vault(self.vault)
            dlg.destroy()
            
        dialog.connect("response", response_cb)
        dialog.show()

    def on_rename_action(self, action, param):
        dialog = Adw.MessageDialog(
            heading="Rename Vault",
            body=f"Enter a new name for '{self.vault.name}'",
            transient_for=self.get_root()
        )
        
        entry = Gtk.Entry()
        entry.set_text(self.vault.name)
        dialog.set_extra_child(entry)
        
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("rename", "Rename")
        dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)
        
        def response_cb(dlg, response):
            if response == "rename":
                new_name = entry.get_text()
                if new_name:
                    self.vault.name = new_name
                    self.update_ui()
                    win = self.get_root()
                    if hasattr(win, 'save_vaults'):
                        win.save_vaults()
            dlg.destroy()
            
        dialog.connect("response", response_cb)
        dialog.show()

    def update_status(self):
        is_unlocked = self.vault.status == VaultStatus.UNLOCKED
        
        if is_unlocked:
            self.status_icon.set_from_icon_name("changes-allow-symbolic")
            self.action_btn.set_icon_name("changes-allow-symbolic")
            self.action_btn.set_tooltip_text("Lock")
            self.action_btn.add_css_class("destructive-action")
            self.action_btn.remove_css_class("suggested-action")
            if self.vault.mount_path:
                self.set_subtitle(f"Mounted at {self.vault.mount_path}")
            self.reveal_btn.set_visible(True)
        else:
            self.status_icon.set_from_icon_name("changes-prevent-symbolic")
            self.action_btn.set_icon_name("changes-prevent-symbolic")
            self.action_btn.set_tooltip_text("Unlock")
            self.action_btn.add_css_class("suggested-action")
            self.action_btn.remove_css_class("destructive-action")
            self.set_subtitle(self.vault.path)
            self.reveal_btn.set_visible(False)

    def on_action_clicked(self, btn):
        win = self.get_root()
        if self.vault.status == VaultStatus.LOCKED:
            # Open Password Dialog
            from password_dialog import PasswordDialog
            pwd_dlg = PasswordDialog(win, self.vault.name)
            
            def response_cb(dlg, response):
                if response == "unlock":
                    password = dlg.get_password()
                    if password:
                        # Call unlock logic (usually in window/backend)
                        self.unlock_vault(password)
                dlg.destroy()
            
            pwd_dlg.connect("response", response_cb)
            pwd_dlg.present()
        else:
            # Lock vault
            self.lock_vault()

    def unlock_vault(self, password):
        # Disable button and show spinner/loading state if possible
        self.action_btn.set_sensitive(False)
        self.action_btn.set_tooltip_text("Unlocking...")
        
        def run_unlock():
            from backend import CryptomatorBackend
            home_dir = os.path.expanduser('~')
            mount_base = os.path.join(home_dir, "mnt", "cryptomator")
            mount_point = os.path.join(mount_base, self.vault.name)
            
            success, actual_mount = CryptomatorBackend.unlock(self.vault.path, password, mount_point)
            
            # Update UI on main thread
            GLib.idle_add(self.on_unlock_finished, success, actual_mount)
            
        threading.Thread(target=run_unlock, daemon=True).start()

    def on_unlock_finished(self, success, actual_mount):
        self.action_btn.set_sensitive(True)
        
        if success:
            self.vault.status = VaultStatus.UNLOCKED
            self.vault.mount_path = actual_mount
            self.update_status()
            # Automatically open file manager on success
            self.on_reveal_clicked(None)
        else:
            self.action_btn.set_tooltip_text("Unlock")
            # Show error toast/dialog
            win = self.get_root()
            if hasattr(win, 'toast_overlay'):
                toast = Adw.Toast.new("Failed to unlock vault")
                win.toast_overlay.add_toast(toast)

    def lock_vault(self):
        from backend import CryptomatorBackend
        if CryptomatorBackend.lock(self.vault.path):
            self.vault.status = VaultStatus.LOCKED
            self.vault.mount_path = None
            self.update_status()

    def on_reveal_clicked(self, btn):
        if self.vault.mount_path:
            uri = f"file://{self.vault.mount_path}"
            Gtk.show_uri(self.get_root(), uri, 0)

    def update_ui(self):
        # Alias for update_status if window calls update_ui
        self.update_status()
        self.set_title(self.vault.name)

