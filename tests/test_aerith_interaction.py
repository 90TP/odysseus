from src.aerith_interaction import AerithInteraction


def test_vision_context_and_history():
    prompts = []

    def llm(prompt):
        prompts.append(prompt)
        return "I can see the screen."

    interaction = AerithInteraction(llm, max_history=1)
    interaction.vision_updated(1, "A browser window is open on the desktop.")

    assert "CURRENT VISUAL PERCEPTION:" in interaction.build_context()
    assert "A browser window is open" in interaction.build_context()

    assert interaction.respond("What is open?") == "I can see the screen."
    assert prompts
    assert "A browser window is open" in prompts[-1]

    state = interaction.snapshot()
    assert state.last_user_message == "What is open?"
    assert state.last_aerith_response == "I can see the screen."
    assert len(state.conversation) == 2


def test_pending_vision_does_not_replace_last_observation():
    interaction = AerithInteraction(lambda prompt: "ok")
    interaction.vision_updated(0, "The terminal is visible.")
    interaction.vision_started()

    context = interaction.build_context()
    assert "The terminal is visible." in context
    assert "currently in progress" in context


def test_action_handler_updates_acting_state_and_returns_result():
    seen = []

    def handler(action, payload):
        seen.append((action, payload))
        return {"ok": True}

    interaction = AerithInteraction(lambda prompt: "ok", action_handler=handler)
    result = interaction.handle_action("click", {"x": 10, "y": 20})

    assert result == {"ok": True}
    assert seen == [("click", {"x": 10, "y": 20})]
    assert interaction.snapshot().acting is False


def test_action_handler_is_required_for_actions():
    interaction = AerithInteraction(lambda prompt: "ok")

    try:
        interaction.handle_action("click")
    except RuntimeError as exc:
        assert "no action handler" in str(exc)
    else:
        raise AssertionError("handle_action should require an action handler")
