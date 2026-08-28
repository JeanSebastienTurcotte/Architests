#Fichier helper
"""
Construction de congruences linéaires a*x ≡ b (mod n) dans Sage.

Rappel théorique :
    Pour la congruence a*x ≡ b (mod n), en posant d = gcd(a, n) :
        - si d ne divise pas b  -> AUCUNE solution
        - si d divise b         -> exactement d classes de solutions modulo n

La fonction construire_congruence() exploite ce fait pour générer, au choix :
    - une congruence sans solution
    - une congruence ayant exactement k classes de solutions (k doit diviser n)
"""

def construire_congruence(n, nb_classes=0, verbose=False):
    """
    Construit une congruence a*x ≡ b (mod n).

    INPUT:
        n          : entier > 0, le module de la congruence
        nb_classes : - None      -> construit une congruence SANS solution
                     - entier k  -> construit une congruence ayant exactement
                                    k classes de solutions modulo n
                                    (k doit être un diviseur de n)
        verbose    : affiche une explication si True

    OUTPUT:
        un triplet (a, b, n) représentant la congruence a*x ≡ b (mod n)
    """
    n = Integer(n)
    if n <= 0:
        raise ValueError("Le module n doit être un entier strictement positif.")

    # ---------- Cas 1 : congruence SANS solution ----------
    if nb_classes==0:
        diviseurs_utiles = [d for d in divisors(n) if d > 1]
        if not diviseurs_utiles:
            raise ValueError(
                f"Impossible : n={n} n'a pas de diviseur > 1 "
                "(il faut n >= 2 pour construire une congruence sans solution)."
            )
        d = choice(diviseurs_utiles)

        # on choisit a tel que gcd(a, n) = d exactement
        while True:
            a_prime = ZZ.random_element(1, 20)
            if gcd(a_prime, n // d) == 1:
                a = d * a_prime
                break

        # on choisit b qui N'EST PAS multiple de d
        while True:
            b = ZZ.random_element(0, 100)
            if b % d != 0:
                break

        if verbose:
            print(f"Congruence SANS solution : {a}*x ≡ {b} (mod {n})")
            print(f"  gcd({a}, {n}) = {d}, mais {d} ne divise pas {b} => aucune solution.")

        return (a, b, n)

    # ---------- Cas 2 : congruence avec exactement k classes de solutions ----------
    else:
        k = Integer(nb_classes)
        if  n % k != 0:
            raise ValueError(f"k={k} doit être un diviseur positif de n={n}.")

        # on choisit a tel que gcd(a, m) = k exactement
        while True:
            a_prime = ZZ.random_element(1, 20)
            if gcd(a_prime, n // k) == 1:
                a = k * a_prime
                break

        # on choisit b multiple de k (b = 0 admis, mais on veut qu'il divise)
        b = k * ZZ.random_element(1, 20)

        if verbose:
            print(f"Congruence avec {k} classe(s) de solution(s) : {a}*x ≡ {b} (mod {n})")
            print(f"  gcd({a}, {n}) = {k}, et {k} divise {b} => exactement {k} solution(s).")

        return (a, b, n)


def verifier_congruence(a, b, m):
    """
    Vérifie par force brute (utile pour m pas trop grand) les solutions
    de a*x ≡ b (mod m) et affiche le nombre de classes trouvées.
    """
    m = Integer(m)
    solutions = [x for x in range(m) if (Integer(a) * x - Integer(b)) % m == 0]
    print(f"Vérification de {a}*x ≡ {b} (mod {m}) :")
    if not solutions:
        print("  -> Aucune solution trouvée. ✓")
    else:
        print(f"  -> {len(solutions)} classe(s) de solution(s) : {solutions}")
    return solutions

