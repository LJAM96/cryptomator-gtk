import os
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib

from vault import Vault, VaultStatus
from row import VaultRow

class MainWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.set_default_size(800, 600)
        self.set_title("Cryptomator-gtk")
        
        self.vaults = [] 
        self._rows = [] 

        # Main content with toast overlay
        self.toast_overlay = Adw.ToastOverlay()
        content = Adw.ToolbarView()
        self.toast_overlay.set_child(content)
        self.set_content(self.toast_overlay)

        # Header bar
        header = Adw.HeaderBar()
        content.add_top_bar(header)
        
        # Add button with menu
        add_menu = Gio.Menu()
        add_menu.append("Add Existing Vault", "win.add_existing")
        add_menu.append("Create New Vault", "win.create_new")
        
        add_btn = Gtk.MenuButton(icon_name="list-add-symbolic")
        add_btn.set_tooltip_text("Add Vault")
        add_btn.set_menu_model(add_menu)
        header.pack_end(add_btn)
        
        # Actions for add menu
        add_existing_action = Gio.SimpleAction.new("add_existing", None)
        add_existing_action.connect("activate", lambda a, p: self.on_add_clicked(None))
        self.add_action(add_existing_action)
        
        create_new_action = Gio.SimpleAction.new("create_new", None)
        create_new_action.connect("activate", self.on_create_new)
        self.add_action(create_new_action)
        
        # Settings button
        settings_btn = Gtk.Button(icon_name="emblem-system-symbolic")
        settings_btn.set_tooltip_text("Settings")
        settings_btn.connect("clicked", self.on_settings_clicked)
        header.pack_end(settings_btn)

        # Stack for switching between empty and list view
        self.stack = Gtk.Stack()
        content.set_content(self.stack)

        # Status Page (Empty State)
        self.status_page = Adw.StatusPage()
        self.status_page.set_title("No Vaults")
        self.status_page.set_description("Add a vault to get started.")
        self.status_page.set_icon_name("io.github.ljam96.CryptomatorGTK") 
        self.stack.add_named(self.status_page, "empty")

        # List view (Preferences Page)
        self.pref_page = Adw.PreferencesPage()
        self.vault_group = Adw.PreferencesGroup()
        self.pref_page.add(self.vault_group)
        self.stack.add_named(self.pref_page, "list")

        self.config_dir = os.path.join(GLib.get_user_config_dir(), "cryptomator-gtk")
        self.vaults_file = os.path.join(self.config_dir, "vaults.json")
        self.load_vaults()
        
        # Restore vault states (detect if still mounted)
        self.restore_vault_states()
        
        self.update_ui_state()
        
        # Auto-mount logic
        GLib.timeout_add(500, self.check_automount) # Small delay to let UI show first or run in BG?
        
        # Connect close request handler
        self.connect("close-request", self.on_close_request)

    def check_automount(self):
        # Load settings to see if automount is enabled
        settings_file = os.path.join(self.config_dir, "settings.json")
        enabled = False
        if os.path.exists(settings_file):
            try:
                import json
                with open(settings_file, 'r') as f:
                    data = json.load(f)
                    enabled = data.get("automount", False)
            except: pass
        
        if enabled:
            self.perform_automount()
        return False
    
    def restore_vault_states(self):
        """Check if vaults are still mounted from previous session"""
        from backend import CryptomatorBackend
        
        for row in self.get_vault_rows():
            vault = row.vault
            # Check if vault has a mount_path saved and if it's still mounted
            if vault.mount_path and CryptomatorBackend.is_mounted(vault.path, vault.mount_path):
                print(f"DEBUG: Vault {vault.name} is still mounted at {vault.mount_path}", flush=True)
                vault.status = VaultStatus.UNLOCKED
                row.update_status()
                # Start monitoring for manual unmounts
                row.start_mount_monitoring()
            else:
                # Not mounted, clear mount_path
                vault.mount_path = None
                vault.status = VaultStatus.LOCKED
                row.update_status()
    
    def on_close_request(self, window):
        """Handle window close request - warn if vaults are unlocked"""
        unlocked_vaults = [row.vault for row in self.get_vault_rows() 
                          if row.vault.status == VaultStatus.UNLOCKED]
        
        if unlocked_vaults:
            # Save vault states before showing dialog
            self.save_vaults()
            
            vault_names = "\n".join([f"• {v.name}" for v in unlocked_vaults])
            dialog = Adw.MessageDialog(
                heading="Vaults Still Unlocked",
                body=f"The following vault(s) are still unlocked and mounted:\n\n{vault_names}\n\n"
                     f"They will remain accessible until you lock them or restart your system. "
                     f"Close anyway?",
                transient_for=self
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("close", "Close Anyway")
            dialog.set_response_appearance("close", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_default_response("cancel")
            
            def on_response(dlg, response):
                if response == "close":
                    # User confirmed, allow close
                    self.destroy()
                dlg.close()
            
            dialog.connect("response", on_response)
            dialog.present()
            return True  # Prevent default close
        
        # No unlocked vaults, save and allow close
        self.save_vaults()
        return False  # Allow default close

    def perform_automount(self):
        import keyring_helper
        from backend import CryptomatorBackend
        
        for row in self.get_vault_rows():
            vault = row.vault
            if vault.status == VaultStatus.LOCKED:
                pwd = keyring_helper.load_password(vault.path)
                if pwd:
                    home_dir = os.path.expanduser('~')
                    home_dir = os.path.expanduser('~')
                    mount_base = os.path.join(home_dir, "mnt", "cryptomator")
                    mount_point = os.path.join(mount_base, vault.name)
                    
                    print(f"Auto-mounting {vault.name}...", flush=True)
                    success, actual_mount = CryptomatorBackend.unlock(vault.path, pwd, mount_point)
                    if success:
                         vault.status = VaultStatus.UNLOCKED
                         vault.mount_path = actual_mount
                         row.update_status()
                         print(f"Auto-mounted {vault.name} at {actual_mount}", flush=True)
                         # Don't auto-open file manager for automount to avoid multiple windows

    def get_vault_rows(self):
        # Helper to iterate rows in vault_group
        # Adw.PreferencesGroup doesn't explicitly expose child list easily via get_children?
        # It inherits from Gtk.Widget, but children are rows.
        # Let's iterate using standard Gtk widget capabilities if needed, 
        # or maintain a list of rows self.rows = []
        # easier to use self.vaults but I need the ROW widget to update status visually?
        # Actually I can update vault object, but Row needs to reflect it.
        # Row has `vault` ref. If I update vault status, I need row to call update_status().
        # I should keep track of rows or find them.
        # Let's just create a list self.rows = [] in init and append.
        return self._rows

    def on_settings_clicked(self, btn):
        from settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.show()


    def load_vaults(self):
        if not os.path.exists(self.vaults_file):
            return
            
        try:
            with open(self.vaults_file, 'r') as f:
                import json
                data = json.load(f)
                for v_data in data:
                    vault = Vault.from_dict(v_data)
                    self.vaults.append(vault)
                    row = VaultRow(vault)
                    self.vault_group.add(row)
                    self._rows.append(row)
        except Exception as e:
            print(f"Failed to load vaults: {e}")

    def save_vaults(self):
        os.makedirs(self.config_dir, exist_ok=True)
        data = [v.to_dict() for v in self.vaults]
        try:
            with open(self.vaults_file, 'w') as f:
                import json
                json.dump(data, f)
        except Exception as e:
            print(f"Failed to save vaults: {e}")
    
    def remove_vault(self, row):
        """Remove a vault from the list"""
        # First, ensure vault is locked
        if row.vault.status == VaultStatus.UNLOCKED:
            # Lock it first
            from backend import CryptomatorBackend
            CryptomatorBackend.lock(row.vault.path)
            row.stop_mount_monitoring()
        
        # Remove from vaults list
        if row.vault in self.vaults:
            self.vaults.remove(row.vault)
        
        # Remove from rows list
        if row in self._rows:
            self._rows.remove(row)
        
        # Remove from UI
        self.vault_group.remove(row)
        
        # Save changes
        self.save_vaults()
        
        # Update UI state
        self.update_ui_state()
        
        # Show toast notification
        if hasattr(self, 'toast_overlay'):
            toast = Adw.Toast.new(f"Removed '{row.vault.name}' from vault list")
            toast.set_timeout(3)
            self.toast_overlay.add_toast(toast)

    def update_ui_state(self):
        if not self.vaults:
            self.stack.set_visible_child_name("empty")
        else:
            self.stack.set_visible_child_name("list")

    def on_add_clicked(self, btn):
        dialog = Gtk.FileChooserNative(
            title="Open Cryptomator Vault",
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            accept_label="_Open",
            cancel_label="_Cancel",
        )
        dialog.connect("response", self.on_add_response)
        dialog.show()
    
    def on_create_new(self, action, param):
        """Show dialog to create a new vault"""
        from create_vault_dialog import CreateVaultDialog
        
        dialog = CreateVaultDialog(self)
        
        def on_response(dlg, response):
            if response == "create":
                vault_name = dialog.get_vault_name()
                vault_location = dialog.get_vault_location()
                password = dialog.get_password()
                confirm_password = dialog.get_confirm_password()
                
                # Validate inputs
                if not vault_name or not vault_location or not password:
                    error = Adw.MessageDialog(
                        heading="Invalid Input",
                        body="Please fill in all fields.",
                        transient_for=self
                    )
                    error.add_response("ok", "OK")
                    error.show()
                    dlg.destroy()
                    return
                
                if password != confirm_password:
                    error = Adw.MessageDialog(
                        heading="Passwords Don't Match",
                        body="The passwords you entered don't match. Please try again.",
                        transient_for=self
                    )
                    error.add_response("ok", "OK")
                    error.show()
                    dlg.destroy()
                    return
                
                if len(password) < 8:
                    error = Adw.MessageDialog(
                        heading="Password Too Short",
                        body="Password must be at least 8 characters long.",
                        transient_for=self
                    )
                    error.add_response("ok", "OK")
                    error.show()
                    dlg.destroy()
                    return
                
                # Create vault path
                vault_path = os.path.join(vault_location, vault_name)
                
                # Show creating dialog
                creating_dialog = Adw.MessageDialog(
                    heading="Creating Vault",
                    body=f"Creating vault '{vault_name}'...\n\nThis may take a moment.",
                    transient_for=self
                )
                creating_dialog.show()
                
                # Create vault in background thread
                def create_vault_thread():
                    try:
                        from vault_creator import VaultCreator
                        success, error_msg = VaultCreator.create_vault(vault_path, password)
                        GLib.idle_add(self.on_vault_created, success, error_msg, vault_path, vault_name, creating_dialog)
                    except Exception as e:
                        GLib.idle_add(self.on_vault_created, False, str(e), vault_path, vault_name, creating_dialog)
                
                import threading
                thread = threading.Thread(target=create_vault_thread, daemon=True)
                thread.start()
                
            dlg.destroy()
        
        dialog.connect("response", on_response)
        dialog.show()
    
    def on_vault_created(self, success, error_msg, vault_path, vault_name, creating_dialog):
        """Handle vault creation completion"""
        creating_dialog.close()
        
        if success:
            # Add vault to list
            vault = Vault(name=vault_name, path=vault_path)
            self.vaults.append(vault)
            self.save_vaults()
            
            row = VaultRow(vault)
            self.vault_group.add(row)
            self._rows.append(row)
            
            self.update_ui_state()
            
            # Show success message
            success_dialog = Adw.MessageDialog(
                heading="Vault Created Successfully!",
                body=f"Your vault '{vault_name}' has been created and is ready to use!\n\n"
                     f"📁 Location: {vault_path}\n"
                     f"🔐 Secured with your password\n\n"
                     f"The vault is fully initialized and can be unlocked immediately. "
                     f"You can now store your sensitive files securely!",
                transient_for=self
            )
            success_dialog.add_response("ok", "OK")
            success_dialog.add_response("unlock_now", "Unlock Now")
            success_dialog.set_response_appearance("unlock_now", Adw.ResponseAppearance.SUGGESTED)
            
            def on_response(dlg, response):
                if response == "unlock_now":
                    # Find the row and trigger unlock
                    for row in self._rows:
                        if row.vault.path == vault_path:
                            row.on_unlock_clicked(None)
                            break
                dlg.destroy()
            
            success_dialog.connect("response", on_response)
            success_dialog.show()
        else:
            # Show error
            error_dialog = Adw.MessageDialog(
                heading="Failed to Create Vault",
                body=f"Could not create vault: {error_msg}",
                transient_for=self
            )
            error_dialog.add_response("ok", "OK")
            error_dialog.show()
        
        return False  # Don't repeat

    def on_add_response(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            folder = dialog.get_file()
            path = folder.get_path()
            name = os.path.basename(path)
            
            # Create vault and row
            vault = Vault(name=name, path=path)
            self.vaults.append(vault)
            self.save_vaults()
            
            row = VaultRow(vault)
            self.vault_group.add(row)
            self._rows.append(row)
            
            self.update_ui_state()
            
        dialog.destroy()
