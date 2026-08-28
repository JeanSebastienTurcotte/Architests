#Helper function. 
#Return the number of steps to find the gcd in the Euclidean algorithm
def Euclidsteps(a,b):
    r=a%b
    q=a//b
    i=1
    while r!=0:
        a=b
        b=r
        r=a%b
        q=a//b
        i+=1
    return i