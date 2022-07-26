from django import template
import decimal

register = template.Library()

@register.filter(name='dollars')
def dollars(pennies):
    # convert pennies to dollars if digit
    if not str(pennies).isdigit():
        return pennies
    cent = decimal.Decimal('0.01')
    dollars = decimal.Decimal(int(pennies)/100).quantize(cent, decimal.ROUND_HALF_UP)
    return f'${dollars}'
