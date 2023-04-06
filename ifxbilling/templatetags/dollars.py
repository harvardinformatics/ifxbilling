# -*- coding: utf-8 -*-

'''
Template tags, mostly for billing emails
'''
import decimal
from django import template

register = template.Library()

@register.filter(name='dollars')
def dollars(pennies):
    ''' convert pennies to dollars if digit '''
    if not str(pennies).isdigit():
        return pennies
    cent = decimal.Decimal('0.01')
    val = decimal.Decimal(int(pennies)/100).quantize(cent, decimal.ROUND_HALF_UP)
    return f'${val}'


@register.filter(name='just_dollars')
def just_dollars(val):
    '''
    Only display as dollars without penny conversion
    '''
    try:
        int(val)
    except ValueError:
        return val
    cent = decimal.Decimal('0.01')
    valstr, signstr = val_sign(decimal.Decimal(val).quantize(cent, decimal.ROUND_HALF_UP))
    return f'{signstr}${valstr}'
