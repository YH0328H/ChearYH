from __future__ import annotations

from threading import Event

from cether.backchannel import BackchannelConfig, BackchannelScheduler


def test_rules_are_ordered_and_handle_checks_cancellation():
    delivered = Event()
    handles = []
    config = BackchannelConfig(rules=(("hello", "问候。"), ("when", "疑问。")))
    scheduler = BackchannelScheduler(lambda handle: (handles.append(handle), delivered.set()), config)
    handle = scheduler.start("hello?")
    assert handle is not None
    assert handle.text == "问候。"
    assert delivered.wait(1)
    assert handles == [handle]
    assert handle.may_enqueue_tts()
    handle.cancel()
    assert not handle.may_enqueue_tts()


def test_no_match_uses_silent_fallback():
    scheduler = BackchannelScheduler(lambda _handle: None, BackchannelConfig(rules=((('hello',), "你好。"),)))
    assert scheduler.start("a routine statement") is None
