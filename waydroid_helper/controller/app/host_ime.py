"""Connect the embedded canvas's GTK input context to the selected guest IME."""

import asyncio
import json
import uuid
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from gettext import gettext as _

from gi.repository import Gdk, Graphene, Gtk

from waydroid_helper.util.log import logger


# The ADB shell owns the temporary IME choice. EOF on its command pipe also
# runs cleanup if the GTK process exits unexpectedly. Respect a newer choice
# the user made in Android, and never write secure settings directly.
_COMMAND_SESSION = r"""
ime_id="$package/.HostIme"
previous=$(settings --user "$user_id" get secure default_input_method) || exit 1
enabled=$(settings --user "$user_id" get secure enabled_input_methods) || exit 1
case ":$enabled:" in *":$ime_id:"*|*":$ime_id;"*) was_enabled=yes ;; *) was_enabled=no ;; esac
restore() {
    current=$(settings --user "$user_id" get secure default_input_method)
    if [ "$current" = "$ime_id" ] && [ "$previous" != "$ime_id" ]; then
        ime set --user "$user_id" "$previous" >/dev/null || return
    fi
    if [ "$was_enabled" = no ]; then ime disable --user "$user_id" "$ime_id" >/dev/null; fi
}
[ -n "$previous" ] && [ "$previous" != null ] || exit 1
trap restore EXIT
trap 'exit 0' HUP TERM
if [ "$previous" != "$ime_id" ]; then
    ime enable --user "$user_id" "$ime_id" >/dev/null &&
        ime set --user "$user_id" "$ime_id" >/dev/null || exit 1
fi
[ "$(settings --user "$user_id" get secure default_input_method)" = "$ime_id" ] || exit 1
# FileUtils.copy() in Android 13's content CLI can batch socket-to-pipe
# splices until more keystrokes or EOF. Give it a pipe on both sides so
# each preedit reaches the editor immediately, including the last commit.
cat | content write --user "$user_id" --uri "$uri"
"""


@asynccontextmanager
async def _content_pipe(serial, user, package, command, uri):
    # Only an integer from ActivityManager and our locally generated hex token
    # enter this shell program. Editor content always travels through stdin.
    script = (f"user_id={int(user)}\npackage={package}\nuri={uri}\n" + _COMMAND_SESSION
              if command == "write" else f"content read --user {int(user)} --uri {uri}")
    proc = await asyncio.create_subprocess_exec(
        "adb", "-s", serial, "shell", "-T", script, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        yield proc
    finally:
        proc.stdin.close()
        if command == "write":
            try:
                await asyncio.wait_for(proc.wait(), 3)
            except TimeoutError:
                logger.warning("Android host IME command pipe did not close on %s", serial)
        if proc.returncode is None:
            with suppress(ProcessLookupError):
                proc.terminate()
        await proc.wait()


class HostIme:
    def __init__(self, window):
        self.window = window
        self.editor = None
        self.writer = None
        self.focused = False
        self.caret = None
        self.click = (0, 0)
        self.context = Gtk.IMMulticontext()
        self.context.set_client_widget(window)
        self.context.connect("commit", lambda _, text: self.send("commit", text))
        self.context.connect("preedit-changed", self._preedit_changed)
        self.keys = Gtk.EventControllerKey()
        self.keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.keys.connect("key-pressed", self._unfiltered_key)
        window.canvas.add_controller(self.keys)
        window.canvas.connect("notify::has-focus", self.sync_focus)
        window.connect("notify::is-active", self.sync_focus)
        window.connect("notify::current-mode", self.sync_focus)
        window.connect("realize", self._watch_layout)

    def _watch_layout(self, window):
        # After GTK allocates the resized toplevel, the canvas transform and
        # letterbox are current even when Android kept its fixed resolution.
        window.get_surface().connect_after("layout", self.update_location)

    async def serve(self, serial, user, package, connected, *, legacy=False):
        """Own one pair of authenticated ADB pipes until disconnection or cancellation."""
        uri = f"content://{package}/{uuid.uuid4().hex}"
        try:
            async with AsyncExitStack() as stack:
                events = await stack.enter_async_context(
                    _content_pipe(serial, user, package, "read", uri + "/events")
                )
                line = await asyncio.wait_for(events.stdout.readline(), 10)
                if not line:
                    raise ConnectionError(_("Android could not open the desktop input method."))
                hello = json.loads(line).get("event")
                if hello == "busy":
                    raise RuntimeError(_("Another emulator window is using the host input method."))
                if hello != "ready":
                    raise ConnectionError(_("Android could not open the desktop input method."))
                commands = await stack.enter_async_context(
                    _content_pipe(serial, user, package, "write", uri + "/commands")
                )
                self.writer = commands.stdin
                if legacy:
                    connected()
                reader = asyncio.create_task(self._read(events.stdout, connected))
                exited = asyncio.create_task(commands.wait())
                try:
                    done, _pending = await asyncio.wait(
                        (reader, exited), return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        task.result()
                finally:
                    for task in (reader, exited):
                        task.cancel()
                    await asyncio.gather(reader, exited, return_exceptions=True)
                raise ConnectionError(_("The desktop input method disconnected."))
        finally:
            self.writer = None
            self._set_editor(None)

    async def _read(self, stream, connected):
        async for line in stream:
            message = json.loads(line)
            event = message.get("event")
            if event == "connected":
                connected()
            elif event == "open":
                self._set_editor(message)
            elif event == "close":
                self._set_editor(None)
            elif event == "reset" and self.editor and message.get("id") == self.editor["id"]:
                # The Android editor moved the selection outside the composing
                # span. Drop the desktop candidate without committing it elsewhere.
                focused = self.focused
                self.focused = False
                self.context.reset()
                self.focused = focused
            elif event == "caret" and self.editor and message.get("id") == self.editor["id"]:
                self.caret = message["rect"]
                self.update_location()

    def _set_editor(self, editor):
        if self.editor and editor and self.editor["id"] == editor["id"]:
            return
        # Reset while the old editor is detached. GTK backends may emit a final
        # commit or empty preedit synchronously from reset/focus_out.
        self.editor = None
        self.sync_focus()
        self.caret = None
        self.editor = editor
        if editor:
            kind = editor["type"]
            purpose = Gtk.InputPurpose.FREE_FORM
            category, variation = kind & 15, kind & 0xff0
            if category == 1:
                purpose = {0x10: Gtk.InputPurpose.URL, 0x20: Gtk.InputPurpose.EMAIL,
                           0x80: Gtk.InputPurpose.PASSWORD, 0x90: Gtk.InputPurpose.PASSWORD,
                           0xe0: Gtk.InputPurpose.PASSWORD}.get(variation, purpose)
            elif category == 2:
                purpose = Gtk.InputPurpose.PIN if variation == 0x10 else Gtk.InputPurpose.NUMBER
            elif category == 3:
                purpose = Gtk.InputPurpose.PHONE
            private = editor["private"] or purpose in (Gtk.InputPurpose.PASSWORD, Gtk.InputPurpose.PIN)
            self.context.props.input_purpose = purpose
            self.context.props.input_hints = Gtk.InputHints.PRIVATE if private else Gtk.InputHints(0)
        self.window._ime_changed(editor is not None)
        self.sync_focus()

    def sync_focus(self, *_):
        active = bool(self.editor and self.window.is_active() and self.window.canvas.has_focus()
                      and self.window.current_mode == self.window.MAPPING_MODE)
        if active == self.focused:
            return
        if active:
            self.focused = True
            self.keys.set_im_context(self.context)
            self.context.focus_in()
            self.update_location()
        else:
            self.send("preedit", "")
            self.focused = False
            self.context.reset()
            self.context.focus_out()
            self.keys.set_im_context(None)

    def clicked(self, x, y):
        self.click = (x, y)
        if self.caret is None:
            self.update_location()

    def update_location(self, *_):
        if not self.focused:
            return
        canvas = self.window.canvas
        x, y = self.click
        bottom = y + 1
        if self.caret:
            width, height = self.window.screen_geometry.get_resolution()
            if width > 0 and height > 0:
                x, y, bottom = self.caret
                x *= canvas.get_width() / width
                y *= canvas.get_height() / height
                bottom *= canvas.get_height() / height
        # GTK IM modules expect client-widget coordinates. Transform through the
        # very same canvas that scales/letterboxes the embedded guest display.
        ok, point = canvas.compute_point(self.window, Graphene.Point().init(x, y))
        ok2, end = canvas.compute_point(self.window, Graphene.Point().init(x, bottom))
        if ok and ok2:
            rect = Gdk.Rectangle()
            rect.x, rect.y = round(point.x), round(point.y)
            rect.width, rect.height = 1, max(1, round(end.y - point.y))
            self.context.set_cursor_location(rect)

    def _preedit_changed(self, context):
        text, _, _ = context.get_preedit_string()
        self.send("preedit", text)

    def send(self, op, text=None):
        if not (self.focused and self.editor and self.writer and not self.writer.is_closing()):
            return
        command = {"id": self.editor["id"], "op": op}
        if text is not None:
            command["text"] = text
        self.writer.write((json.dumps(command, ensure_ascii=False) + "\n").encode())

    def _unfiltered_key(self, controller, keyval, keycode, state):
        # The native event controller offers keys to Fcitx/IBus first. Enter and
        # Escape reach here only after the IM declined to select/cancel a candidate.
        if self.focused and keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_Escape):
            self.send("hide" if keyval == Gdk.KEY_Escape else "enter")
            return True
        return False
