import os
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw

class CreateVaultDialog(Adw.MessageDialog):
    def __init__(self, parent, **kwargs):
        super().__init__(
            transient_for=parent,
            heading="Create New Vault",
            body="Enter a name and choose a location for your new vault.",
            **kwargs
        )
        
        self.add_response("cancel", "Cancel")
        self.add_response("create", "Create")
        self.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
        self.set_default_response("create")
        
        # Create form
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        
        # Vault name entry
        name_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        name_label = Gtk.Label(label="Vault Name:", xalign=0)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_placeholder_text("My Vault")
        name_box.append(name_label)
        name_box.append(self.name_entry)
        box.append(name_box)
        
        # Location chooser
        location_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        location_label = Gtk.Label(label="Location:", xalign=0)
        
        chooser_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.location_entry = Gtk.Entry()
        self.location_entry.set_placeholder_text("Choose a folder...")
        self.location_entry.set_hexpand(True)
        self.location_entry.set_editable(False)
        
        browse_btn = Gtk.Button(label="Browse...")
        browse_btn.connect("clicked", self.on_browse_clicked)
        
        chooser_box.append(self.location_entry)
        chooser_box.append(browse_btn)
        
        location_box.append(location_label)
        location_box.append(chooser_box)
        box.append(location_box)
        
        # Password entry
        password_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        password_label = Gtk.Label(label="Password:", xalign=0)
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        password_box.append(password_label)
        password_box.append(self.password_entry)
        box.append(password_box)
        
        # Confirm password entry
        confirm_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        confirm_label = Gtk.Label(label="Confirm Password:", xalign=0)
        self.confirm_entry = Gtk.PasswordEntry()
        self.confirm_entry.set_show_peek_icon(True)
        confirm_box.append(confirm_label)
        confirm_box.append(self.confirm_entry)
        box.append(confirm_box)
        
        self.set_extra_child(box)
        
        self.selected_folder = None
    
    def on_browse_clicked(self, btn):
        dialog = Gtk.FileChooserNative(
            title="Select Location for New Vault",
            transient_for=self.get_transient_for(),
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            accept_label="_Select",
            cancel_label="_Cancel",
        )
        dialog.connect("response", self.on_folder_selected)
        dialog.show()
    
    def on_folder_selected(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            folder = dialog.get_file()
            self.selected_folder = folder.get_path()
            self.location_entry.set_text(self.selected_folder)
        dialog.destroy()
    
    def get_vault_name(self):
        return self.name_entry.get_text()
    
    def get_vault_location(self):
        return self.selected_folder
    
    def get_password(self):
        return self.password_entry.get_text()
    
    def get_confirm_password(self):
        return self.confirm_entry.get_text()
