#!/usr/bin/python

#import math
#x = float('nan')
#if math.isnan(x):
   #print("True")


def is_nan(x):
    return (x != x)



x = float('nan')
 
if(is_nan(x)):
    print("x is, in fact, nan")
else:
    print("x is not nan")
