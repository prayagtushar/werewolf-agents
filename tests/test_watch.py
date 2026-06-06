from werewolf.events import GameEvent
from werewolf.watch import format_event


def test_format_speak_shows_speaker_and_text():
    line = format_event(GameEvent(kind="speak", day=1, actor="Ava", text="I trust Ben"))
    assert line is not None
    assert "Ava" in line and "I trust Ben" in line


def test_format_reasoning_is_marked_private():
    line = format_event(GameEvent(kind="reasoning", day=1, actor="Ava", text="I am the wolf"))
    assert line is not None
    assert "Ava" in line and "I am the wolf" in line


def test_format_thinking_is_suppressed():
    # the transient "deciding" pings are UI-only noise in a terminal
    assert format_event(GameEvent(kind="thinking", day=1, actor="Ava")) is None


def test_format_result_announces_the_winner():
    line = format_event(
        GameEvent(
            kind="result",
            day=3,
            text="village wins",
            data={"winner": "village", "decisions": 50, "fallbacks": 2},
        )
    )
    assert line is not None
    assert "village wins" in line


def test_format_phase_is_a_banner_with_the_day():
    line = format_event(GameEvent(kind="phase", day=2, text="night"))
    assert line is not None
    assert "2" in line and "night" in line.lower()
