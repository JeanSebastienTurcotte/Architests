# helpers/tf_randomizer.sage

def tf_randomizer(true_text, false_text):
    """
    Randomly choose between two phrasings for a True/False question.
    Returns (statement, answer).
    The seed is controlled externally by the builder's question_seed.
    """
    if random() < 0.5:
        return true_text, True
    else:
        return false_text, False
