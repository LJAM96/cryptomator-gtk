import os
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GObject, Gio, GLib
from vault import Vault, VaultStatus
from backend import CryptomatorBackend

class VaultRow(Adw.ActionRow):
    __gtype_name__ = 'VaultRow'

    def __init__(self, vault: Vault, **kwargs):
        super().__init__(**kwargs)
        self.vault = vault
        
        self.set_title(vault.name)
        self.set_subtitle(vault.path)
        
        # Suffix widget (Button)
        suffix_box = Gtk.Box(spacing=6)
        
        self.action_btn = Gtk.Button(valign=Gtk.Align.CENTER)
        self.action_btn.connect("clicked", self.on_action_clicked)
        suffix_box.append(self.action_btn)
        
        self.reveal_btn = Gtk.Button(icon_name="folder-open-symbolic")
        self.reveal_btn.set_tooltip_text("Reveal in File Manager")
        self.reveal_btn.set_valign(Gtk.Align.CENTER)
        self.reveal_btn.set_visible(False)
        self.reveal_btn.connect("clicked", self.on_reveal)
        suffix_box.append(self.reveal_btn)
        
        # Menu Button for More Actions
        menu = Gio.Menu()
        menu.append("Rename", "row.rename")
        menu.append("Remove", "row.remove")
        
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("view-more-symbolic")
        menu_btn.set_menu_model(menu)
        menu_btn.set_valign(Gtk.Align.CENTER)
        
        # Actions
        action_group = Gio.SimpleActionGroup()
        self.insert_action_group("row", action_group)
        
        rename_action = Gio.SimpleAction.new("rename", None)
        rename_action.connect("activate", self.on_rename)
        action_group.add_action(rename_action)
        
        remove_action = Gio.SimpleAction.new("remove", None)
        remove_action.connect("activate", self.on_remove)
        action_group.add_action(remove_action)

        suffix_box.append(menu_btn)
        self.add_suffix(suffix_box)
        
        # Add double-click gesture to unlock/lock vault
        gesture = Gtk.GestureClick.new()
        gesture.set_button(1)  # Left mouse button
        gesture.connect("released", self.on_row_clicked)
        self.add_controller(gesture)
        
        self.update_status()

    def update_status(self):
        if self.vault.status == VaultStatus.LOCKED:
            self.action_btn.set_icon_name("changes-prevent-symbolic")
            self.action_btn.set_tooltip_text("Unlock")
            self.action_btn.remove_css_class("destructive-action")
            self.action_btn.add_css_class("suggested-action")
            self.set_subtitle(self.vault.path)
            if hasattr(self, 'reveal_btn'):
                self.reveal_btn.set_visible(False)
        elif self.vault.status == VaultStatus.UNLOCKED:
            self.action_btn.set_icon_name("changes-allow-symbolic")
            self.action_btn.set_tooltip_text("Lock")
            self.action_btn.remove_css_class("suggested-action")
            self.action_btn.add_css_class("destructive-action")
            if self.vault.mount_path:
                self.set_subtitle(f"Mounted at {self.vault.mount_path}")
                # Add a Reveal button to the suffix box if not already there?
                # Simpler: Modify action to be just Lock, but add a new button "folder-open-symbolic" to suffix box only when unlocked.
                # However, rebuilding dynamic widgets in update_status is tricky.
                # Let's add the button in init and hide/show it.
                if hasattr(self, 'reveal_btn'):
                    self.reveal_btn.set_visible(True)
    
    def on_reveal(self, btn):
        if self.vault.mount_path:
            # Use specific portal call or Gio.AppInfo.launch_default_for_uri
            # 'file://' uri
            uri = f"file://{self.vault.mount_path}"
            Gtk.show_uri(self.get_root(), uri, 0)
    
    def on_remove(self, action, param):
        """Remove vault from the list (does not delete vault files)"""
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
                # Get the window and remove this vault
                win = self.get_root()
                if hasattr(win, 'remove_vault'):
                    win.remove_vault(self)
            dlg.destroy()
            
        dialog.connect("response", response_cb)
        dialog.show()
    
    def on_row_clicked(self, gesture, n_press, x, y):
        """Handle row clicks - double-click triggers unlock/lock"""
        if n_press == 2:  # Double click
            # Simulate clicking the action button
            self.on_action_clicked(None)
    
    def on_rename(self, action, param):
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
        
        def response_cb(dialog, response):
            if response == "rename":
                new_name = entry.get_text()
                if new_name:
                    self.vault.name = new_name
                    self.set_title(new_name)
                    # Trigger save in parent window (via custom signal or callback)
                    # Getting root (window) and calling save is acceptable for this scale
                    win = self.get_root()
                    if hasattr(win, 'save_vaults'):
                        win.save_vaults()
            dialog.destroy()
            
        dialog.connect("response", response_cb)
        dialog.show()

    
    def on_action_clicked(self, btn):
        if self.vault.status == VaultStatus.LOCKED:
            from password_dialog import PasswordDialog
            import keyring_helper
            
            # Find parent window
            root = self.get_root()
            
            dialog = PasswordDialog(root, self.vault.name)
            
            # Try to load password
            saved_password = keyring_helper.load_password(self.vault.path)
            if saved_password:
                dialog.password_entry.set_text(saved_password)
                dialog.save_check.set_active(True)
            
            dialog.connect("response", self.on_password_response)
            dialog.show()
        else:
            # Lock logic
            self.stop_mount_monitoring()
            if CryptomatorBackend.lock(self.vault.path):
                self.vault.status = VaultStatus.LOCKED
                self.vault.mount_path = None
                self.update_status()

    def on_password_response(self, dialog, response):
        if response == "unlock":
            password = dialog.get_password()
            save_pwd = dialog.get_save_password()
            
            print(f"DEBUG: Unlock requested for vault: {self.vault.name}", flush=True)
            
            # Determine mount point - use ~/mnt/cryptomator/ directory
            home_dir = os.path.expanduser('~')
            mount_base = os.path.join(home_dir, "mnt", "cryptomator")
            mount_point = os.path.join(mount_base, self.vault.name)
            
            print(f"DEBUG: Mount point: {mount_point}", flush=True)
            print(f"DEBUG: Vault path: {self.vault.path}", flush=True)
            
            # Show loading state
            self.action_btn.set_sensitive(False)
            self.action_btn.set_icon_name("content-loading-symbolic")
            original_subtitle = self.get_subtitle()
            self.set_subtitle("Unlocking...")
            
            # Run unlock in background thread
            def unlock_thread():
                try:
                    success, actual_mount = CryptomatorBackend.unlock(self.vault.path, password, mount_point)
                    GLib.idle_add(self.on_unlock_complete, success, actual_mount, password, save_pwd, original_subtitle)
                except Exception as e:
                    GLib.idle_add(self.on_unlock_error, e, original_subtitle)
            
            import threading
            thread = threading.Thread(target=unlock_thread, daemon=True)
            thread.start()
            
        dialog.destroy()
    
    def on_unlock_complete(self, success, actual_mount, password, save_pwd, original_subtitle):
        self.action_btn.set_sensitive(True)
        
        try:
            if success:
                print(f"DEBUG: Backend.unlock returned True", flush=True)
                self.vault.status = VaultStatus.UNLOCKED
                self.vault.mount_path = actual_mount
                self.update_status()
                
                # Start monitoring for manual unmount
                self.start_mount_monitoring()
                
                # Handle keyring
                import keyring_helper
                if save_pwd:
                    keyring_helper.save_password(self.vault.path, password)
                else:
                    keyring_helper.delete_password(self.vault.path)
                
                # Open file manager to show the mounted vault
                if actual_mount:
                    print(f"DEBUG: Opening file manager for {actual_mount}", flush=True)
                    # Simple approach: just show URI without D-Bus complexity
                    try:
                        uri = f"file://{actual_mount}"
                        print(f"DEBUG: Attempting to open URI: {uri}", flush=True)
                        Gtk.show_uri(self.get_root(), uri, 0)
                        print(f"DEBUG: URI opened successfully", flush=True)
                    except Exception as e:
                        print(f"DEBUG: show_uri failed: {e}", flush=True)
                        import traceback
                        traceback.print_exc()
                
            else:
                # Show error dialog and toast
                print("DEBUG: Backend.unlock returned False - FAILED", flush=True)
                print("DEBUG: Showing error dialog to user", flush=True)
                
                # Restore original state
                self.set_subtitle(original_subtitle)
                self.update_status()
                
                # Show toast notification
                window = self.get_root()
                if hasattr(window, 'toast_overlay'):
                    toast = Adw.Toast.new("Incorrect password. Please try again.")
                    toast.set_timeout(3)
                    window.toast_overlay.add_toast(toast)
                
                # Show error dialog
                error_dialog = Adw.MessageDialog(
                    heading="Unlock Failed",
                    body="The password you entered is incorrect. Please try again.",
                    transient_for=self.get_root()
                )
                error_dialog.add_response("ok", "OK")
                error_dialog.set_default_response("ok")
                error_dialog.show()
                print("DEBUG: Error dialog shown", flush=True)
        except Exception as e:
            print(f"ERROR: Exception during unlock complete: {e}", flush=True)
            import traceback
            traceback.print_exc()
        
        return False  # Don't repeat
    
    def on_unlock_error(self, error, original_subtitle):
        self.action_btn.set_sensitive(True)
        self.set_subtitle(original_subtitle)
        self.update_status()
        
        print(f"ERROR: Exception during unlock: {error}", flush=True)
        import traceback
        traceback.print_exc()
        
        # Show error dialog
        error_dialog = Adw.MessageDialog(
            heading="Unlock Error",
            body=f"An error occurred while unlocking the vault:\n{str(error)}",
            transient_for=self.get_root()
        )
        error_dialog.add_response("ok", "OK")
        error_dialog.set_default_response("ok")
        error_dialog.show()
        
        return False  # Don't repeat
    
    def start_mount_monitoring(self):
        """Monitor mount point to detect manual unmounts"""
        if not hasattr(self, '_mount_monitor_id') or self._mount_monitor_id is None:
            self._mount_monitor_id = GLib.timeout_add_seconds(2, self.check_mount_status)
    
    def stop_mount_monitoring(self):
        """Stop monitoring the mount"""
        if hasattr(self, '_mount_monitor_id') and self._mount_monitor_id:
            GLib.source_remove(self._mount_monitor_id)
            self._mount_monitor_id = None
    
    def check_mount_status(self):
        """Check if vault is still mounted"""
        if self.vault.status == VaultStatus.UNLOCKED and self.vault.mount_path:
            # Check if mount point still has content (simple check)
            if not os.path.ismount(self.vault.mount_path):
                # Check if the directory is empty or inaccessible
                try:
                    # If we can't access it or it's been unmounted, update status
                    if not os.path.exists(self.vault.mount_path) or len(os.listdir(self.vault.mount_path)) == 0:
                        print(f"DEBUG: Detected manual unmount of {self.vault.name}", flush=True)
                        self.vault.status = VaultStatus.LOCKED
                        self.vault.mount_path = None
                        self.update_status()
                        
                        # Clean up backend tracking
                        if self.vault.path in CryptomatorBackend._instances:
                            del CryptomatorBackend._instances[self.vault.path]
                        
                        # Show notification
                        window = self.get_root()
                        if hasattr(window, 'toast_overlay'):
                            toast = Adw.Toast.new(f"{self.vault.name} was unmounted")
                            toast.set_timeout(3)
                            window.toast_overlay.add_toast(toast)
                        
                        self.stop_mount_monitoring()
                        return False  # Stop monitoring
                except:
                    pass
            
            return True  # Continue monitoring
        else:
            self.stop_mount_monitoring()
            return False  # Stop monitoring
