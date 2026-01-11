import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw

class PasswordDialog(Adw.MessageDialog):
    def __init__(self, parent, vault_name, **kwargs):
        super().__init__(**kwargs)
        self.set_transient_for(parent)
        self.set_heading(f"Unlock {vault_name}")
        self.set_body("Enter the password for this vault.")
        
        # Password Entry
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.props.activates_default = True
        self.password_entry.set_show_peek_icon(True)
        
        # Save Password Checkbox
        self.save_check = Gtk.CheckButton(label="Save Password")
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(self.password_entry)
        box.append(self.save_check)
        
        self.set_extra_child(box)
        
        self.add_response("cancel", "Cancel")
        self.add_response("unlock", "Unlock")
        
        self.set_response_appearance("unlock", Adw.ResponseAppearance.SUGGESTED)
        self.set_default_response("unlock")
        self.set_close_response("cancel")

    def get_password(self):
        return self.password_entry.get_text()

    def get_save_password(self):
        return self.save_check.get_active()
