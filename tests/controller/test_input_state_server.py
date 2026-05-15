from __future__ import annotations

from waydroid_helper.controller.core.input_state_server import AndroidInputStateServer


def decode(line: bytes):
    server = object.__new__(AndroidInputStateServer)
    return server._decode_state(line)


def test_decode_bridge_text_input_state_message():
    state = decode(
        b'{"type":"text_input_state","active":true,'
        b'"reason":"TYPE_VIEW_FOCUSED:event-source-editable",'
        b'"packageName":"com.android.launcher3","className":"android.widget.EditText"}'
    )

    assert state is not None
    assert state.is_input_active is True
    assert state.reason == "TYPE_VIEW_FOCUSED:event-source-editable"
    assert state.package_name == "com.android.launcher3"
    assert state.class_name == "android.widget.EditText"


def test_decode_legacy_input_active_message():
    state = decode(b'{"inputActive":false,"reason":"no-editable-focus"}')

    assert state is not None
    assert state.is_input_active is False
    assert state.reason == "no-editable-focus"


def test_decode_rejects_unknown_message_type():
    assert decode(b'{"type":"other","active":true}') is None
