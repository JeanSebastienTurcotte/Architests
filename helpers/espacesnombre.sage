#Fichier Helper
""" 
Fonction qui prend un nombre ou une chaine de caractères et qui la sépare en bloc de esp. Par exemple, 
"""

def espacesnombre(n,esp=3):
    espn=""
    n=str(n)
    i=1
    for c in n[::-1]:
        if i%esp ==1 and espn!="":
            espn="\,"+espn
        espn=c+espn
        i+=1
    return espn