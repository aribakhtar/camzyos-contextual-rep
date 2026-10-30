from evals.context_checks import language_of


def test_fixed_english_handoff_does_not_become_german_due_to_hcp_preference():
    result = language_of("I cannot advise on an individual patient's treatment. An MSL or Medical Information can help.")
    assert result["language"] == "English"


def test_language_detection_uses_only_answer_text_and_can_abstain():
    assert language_of("Hier finden Sie eine kurze Zusammenfassung der Informationen aus dem vorliegenden Dokument.")["language"] == "German"
    assert language_of("Here is a short summary of the information in the supplied document.")["language"] == "English"
    assert language_of("CAMZYOS")["language"] is None
