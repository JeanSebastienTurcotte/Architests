# helpers/tf_randomizer.sage

def tf_randomizer(true_text, false_text):
    """
    Choix aléatoire entre deux versions d'un vrai ou faux, par exemple avec ou sans négation.
    Retourne l'énoncé et la valeur de vérité. 
    
    Randomly choose between two phrasings for a True/False question.
    Returns (statement, answer).
    The seed is controlled externally by the builder's question_seed.
    """
    if random() < 0.5:
        return true_text, True
    else:
        return false_text, False
