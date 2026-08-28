# helpers/hexatobinary.sage

def hexatobinary(hexa): #Prend une chaine de caractère hexadécimale et retourne la chaine binaire
    dico={"0":"0000","1":"0001","2":"0010","3":"0011","4":"0100","5":"0101","6":"0110","7":"0111","8":"1000","9":"1001","A":"1010","B":"1011","C":"1100","D":"1101","E":"1110","F":"1111"}
    binstr=""
    for h in hexa:
        binstr+=(dico[h])
    i=0
    while binstr[i]=="0":
        i+=1
    return binstr[i:]