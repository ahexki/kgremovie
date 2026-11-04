"""A stand-in for tkinter so the App window logic can be tested without a screen (the test sandbox has no Tk).

install() puts fake `tkinter`, `tkinter.ttk`, `tkinter.filedialog`, `tkinter.messagebox` modules into sys.modules; every widget
accepts any option and method used by the app. It checks LOGIC (settings, positions, dragging), not how the window looks."""
from __future__ import annotations

import sys
import types


class Var:
    def __init__(self, master=None, value=None, **k):
        self._v = value

    def get(self):
        return self._v

    def set(self, v):
        self._v = v

    def trace_add(self, *a, **k):
        pass


class Widget:
    _TK = {"grid", "pack", "place", "winfo", "bind", "after", "update", "option", "tk", "wm", "focus", "protocol", "title",
           "geometry", "minsize", "resizable", "configure", "config", "columnconfigure", "rowconfigure", "iconbitmap", "destroy",
           "mainloop", "withdraw", "deiconify", "lift", "attributes", "state", "clipboard", "event", "selection", "image", "grab",
           "tkraise", "quit", "insert", "delete", "see", "yview", "xview", "create", "coords", "itemconfigure", "tag", "add",
           "select", "set", "get", "current", "invoke", "identify", "index", "curselection", "heading", "column", "item", "bbox",
           "move", "scale", "canvasx", "canvasy", "map", "theme", "lookup", "layout", "element", "unbind", "wait", "nametowidget",
           "children", "master", "values", "start", "stop", "step", "find", "gettags", "tag_bind", "tag_raise", "tag_lower"}

    def __init__(self, *a, **k):
        self.kw = k

    def __getattr__(self, name):
        if name.startswith("__") or name.split("_")[0] not in self._TK:
            raise AttributeError(name)
        return lambda *a, **k: self

    def winfo_children(self):
        return []

    def winfo_width(self):
        return 800

    def winfo_height(self):
        return 600

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    def after(self, *a, **k):
        return "x"

    def cget(self, *a):
        return ""

    def __getitem__(self, k):
        return ""

    def __setitem__(self, k, v):
        pass


def install() -> None:
    tk = types.ModuleType("tkinter")
    for name in ("Tk", "Frame", "Label", "Canvas", "Toplevel", "Text", "Menu", "Listbox", "Scrollbar", "PanedWindow", "Button",
                 "Entry", "Checkbutton", "Scale", "Spinbox"):
        setattr(tk, name, type(name, (Widget,), {}))
    tk.StringVar = tk.BooleanVar = tk.DoubleVar = tk.IntVar = Var
    tk.END, tk.NORMAL, tk.DISABLED, tk.TclError = "end", "normal", "disabled", Exception
    tk.W, tk.E, tk.N, tk.S = "w", "e", "n", "s"
    ttk = types.ModuleType("tkinter.ttk")
    for name in ("Frame", "Label", "Button", "Entry", "Combobox", "Checkbutton", "Scale", "Scrollbar", "Separator", "LabelFrame",
                 "Notebook", "Progressbar", "Style", "PanedWindow", "Treeview", "Radiobutton", "Spinbox", "Sizegrip"):
        setattr(ttk, name, type(name, (Widget,), {}))
    fd, mb = types.ModuleType("tkinter.filedialog"), types.ModuleType("tkinter.messagebox")
    tk.ttk, tk.filedialog, tk.messagebox = ttk, fd, mb
    sys.modules.update({"tkinter": tk, "tkinter.ttk": ttk, "tkinter.filedialog": fd, "tkinter.messagebox": mb})
