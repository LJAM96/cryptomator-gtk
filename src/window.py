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
        
        self.set_default_size(550, 600)
        self.set_title("Locker")
        
        self.vaults = [] 
        self._rows = [] 

        # Main content with toast overlay
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        # Toolbar View
        self.toolbar_view = Adw.ToolbarView()
        self.toast_overlay.set_child(self.toolbar_view)
        
        # Header Bar
        header = Adw.HeaderBar()
        self.toolbar_view.add_top_bar(header)
        
        # Menu Button
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_menu_model(self.create_menu_model())
        header.pack_end(menu_btn)
        
        # Add Button (Menu Button for Open/Create)
        add_btn = Gtk.MenuButton()
        add_btn.set_icon_name("list-add-symbolic")
        add_btn.set_menu_model(self.create_add_menu_model())
        header.pack_start(add_btn)
        
        # Register window actions
        self.setup_actions()

        # Stack for Empty vs List
        self.stack = Gtk.Stack()
        self.toolbar_view.set_content(self.stack)

        # Status Page (Empty State)
        self.status_page = Adw.StatusPage()
        self.status_page.set_title("No Vaults")
        self.status_page.set_description("Add a vault to get started.")
        self.status_page.set_icon_name("io.github.ljam96.locker") 
        self.stack.add_named(self.status_page, "empty")

        # List view (Preferences Page used as a list container)
        self.pref_page = Adw.PreferencesPage()
        
        # We need a group to hold the rows
        self.vaults_group = Adw.PreferencesGroup()
        self.pref_page.add(self.vaults_group)
        
        self.stack.add_named(self.pref_page, "list")

        self.config_dir = os.path.join(GLib.get_user_config_dir(), "locker")
        self.migrate_data()
        self.vaults_file = os.path.join(self.config_dir, "vaults.json")
        self.load_vaults()
        
        # Restore vault states (detect if still mounted)
        self.restore_vault_states()
        
        self.update_ui_state()
        
        # Auto-mount logic
        GLib.timeout_add(500, self.check_automount) # Small delay to let UI show first or run in BG?
        
        # Connect close request handler
        self.connect("close-request", self.on_close_request)

    def migrate_data(self):
        """Migrate data from old config locations to the new 'locker' directory"""
        if os.path.exists(self.config_dir):
            # Already exists, check if it's empty
            if os.listdir(self.config_dir):
                return

        # Possible old locations
        old_dirs = [
            os.path.join(GLib.get_user_config_dir(), "cryptomator-gtk"),
            os.path.expanduser("~/.var/app/io.github.ljam96.cryptomatorgtk/config/cryptomator-gtk")
        ]
        
        import shutil
        for old_dir in old_dirs:
            if os.path.exists(old_dir) and os.path.isdir(old_dir):
                if not os.path.exists(self.config_dir):
                    os.makedirs(self.config_dir, exist_ok=True)
                
                for item in os.listdir(old_dir):
                    s = os.path.join(old_dir, item)
                    d = os.path.join(self.config_dir, item)
                    if os.path.isfile(s) and not os.path.exists(d):
                        try:
                            shutil.copy2(s, d)
                        except: pass
                break

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
        # Helper to iterate rows in vaults_group
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

    def on_settings_clicked(self, action, param):
        from settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.set_visible(True)


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
                    self.vaults_group.add(row)
                    self._rows.append(row)
                    
                    # Connect activation
                    row.connect("activated", self.on_row_activated)
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
    
    def remove_vault(self, vault):
        """Remove a vault from the list"""
        # Find the row for this vault
        row = next((r for r in self._rows if r.vault == vault), None)
        if not row:
            return

        # First, ensure vault is locked (backend logic)
        if vault.status == VaultStatus.UNLOCKED:
            from backend import CryptomatorBackend
            CryptomatorBackend.lock(vault.path)
            # Monitoring is now in VaultView, which calls this. 
            # VaultView should handle its own stopping.
        
        # Remove from vaults list
        if vault in self.vaults:
            self.vaults.remove(vault)
        
        # Remove from rows list
        if row in self._rows:
            self._rows.remove(row)
        
        # Remove from UI
        self.vaults_group.remove(row)
        
        # Save changes
        self.save_vaults()
        
        # Update UI state
        self.update_ui_state()
        
        # Show toast notification
        if hasattr(self, 'toast_overlay'):
            toast = Adw.Toast.new(f"Removed '{vault.name}' from vault list")
            toast.set_timeout(3)
            self.toast_overlay.add_toast(toast)

    def update_ui_state(self):
        if not self.vaults:
            self.stack.set_visible_child_name("empty")
        else:
            self.stack.set_visible_child_name("list")

    def on_add_clicked(self, action, param):
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
            row.set_activatable(True)
            row.connect("activated", self.on_row_activated)
            self.vaults_group.add(row)
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
                            # Navigate to page
                            self.on_row_activated(row)
                            # Can we auto-trigger unlock? 
                            # The view creates a new instance. We can't easily reach it unless on_row_activated returned it.
                            # But we can just leave it as user needs to click unlock button on the new page.
                            # Or we can push and then find the page.
                            # Simpler: just navigate. The user will see the big "Unlock" button.
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

    def create_menu_model(self):
        menu = Gio.Menu()
        menu.append("Preferences", "win.preferences")
        menu.append("Keyboard Shortcuts", "win.shortcuts")
        menu.append("About Cryptomator", "win.about")
        return menu

    def create_add_menu_model(self):
        menu = Gio.Menu()
        menu.append("Open Existing Vault...", "win.add-existing")
        menu.append("Create New Vault...", "win.create-new")
        return menu

    def setup_actions(self):
        # Add Existing
        action = Gio.SimpleAction.new("add-existing", None)
        action.connect("activate", self.on_add_clicked)
        self.add_action(action)
        
        # Create New
        action = Gio.SimpleAction.new("create-new", None)
        action.connect("activate", self.on_create_new)
        self.add_action(action)
        
        # About
        action = Gio.SimpleAction.new("about", None)
        action.connect("activate", self.show_about)
        self.add_action(action)

        # Settings
        action = Gio.SimpleAction.new("preferences", None)
        action.connect("activate", self.on_settings_clicked)
        self.add_action(action)

    def on_row_activated(self, row):
        # Navigation disabled in single-page mode
        pass

    def update_list_ui(self):
        # Refresh the rows in the main list to reflect status changes
        # For now, we might just need to update the specific row if we had a reference, 
        # but simpler to just reload or if we have the row object, call update.
        # Since we don't keep a map of rows easily, let's just iterate or rely on the fact that
        # the row objects are alive. 
        # Actually, VaultRow listens to nothing? VaultRow needs to update itself?
        # Let's make VaultRow have an update method and call it.
        for row in self._rows:
            if hasattr(row, 'update_ui'):
                row.update_ui()
            # Or re-create list? Re-creating is safer but heavier.
            # Let's try to find the row for the Vault and update it.
            # Ideally the Row should listen to Vault changes or we notify it.
        pass
        
    def show_about(self, action, param):
        dialog = Adw.AboutDialog(
            application_name="Locker",
            application_icon="io.github.ljam96.locker",
            developer_name="ljam96",
            version="0.1.6",
            copyright="© 2024-2026 ljam96",
            website="https://github.com/ljam96/cryptomator-gtk",
            issue_url="https://github.com/ljam96/cryptomator-gtk/issues",
            license_type=Gtk.License.GPL_3_0,
            comments="Simple GTK frontend for Cryptomator CLI. \n\nPowered by Cryptomator. All credit to the Cryptomator team for the encryption backend.",
        )
        dialog.present(self)

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
            row.set_activatable(True)
            row.connect("activated", self.on_row_activated)
            self.vaults_group.add(row)
            self._rows.append(row)
            
            self.update_ui_state()
            
        dialog.destroy()
