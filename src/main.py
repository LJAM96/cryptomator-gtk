import sys
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio

from window import MainWindow

class CryptomatorApp(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.props.application_id = 'io.github.ljam96.locker'
        self.props.flags |= Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        GLib.set_application_name("Locker")

        self.add_main_option("background", ord("b"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "Start in background", None)

    def do_command_line(self, command_line):
        options = command_line.get_options_dict()
        self.start_in_background = options.contains("background")
        self.activate()
        return 0

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = MainWindow(application=self)
        
        if getattr(self, 'start_in_background', False):
            pass # Keep window hidden
        else:
            win.present()
        
        self.start_in_background = False

if __name__ == '__main__':
    try:
        app = CryptomatorApp()
        app.run(sys.argv)
    except Exception as e:
        print(f"FATAL ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
