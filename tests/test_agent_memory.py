from werewolf.agents.memory import AgentMemory


def test_memory_renders_observations_in_order():
    mem = AgentMemory()
    mem.add("You are the Seer.")
    mem.add("Night 1: you investigated Bob -> NOT a werewolf.")
    rendered = mem.render()
    assert "Seer" in rendered
    assert rendered.index("Seer") < rendered.index("Bob")
    assert rendered.startswith("- ")


def test_memory_empty_render():
    assert AgentMemory().render() == ""
