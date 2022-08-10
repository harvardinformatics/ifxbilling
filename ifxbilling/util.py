# -*- coding: utf-8 -*-

'''
utility functions

Created on  2021-10-01

@author: Meghan Correa <mportermahoney@g.harvard.edu>
@copyright: 2021 The President and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from decimal import Decimal, ROUND_HALF_UP
from importlib import import_module

def dollars_num(pennies):
    '''
    convert pennies to dollars number
    '''
    if not str(abs(int(pennies))).isdigit():
        return pennies
    cent = Decimal('0.01')
    dollars = Decimal(int(pennies)/100).quantize(cent, ROUND_HALF_UP)
    return dollars

def dollars(pennies, dollar_sign = True):
    '''
    convert pennies to dollars if digit
    '''
    dollars = str(dollars_num(pennies))
    if dollar_sign:
        dollars = f'${dollars}'
    return dollars

def time_intervals_overlap_seconds(t1_start, t1_end, t2_start, t2_end):
    '''
    check if two time intervals overlap
    '''
    latest_start = max(t1_start, t2_start)
    earliest_end = min(t1_end, t2_end)
    delta = (earliest_end - latest_start).total_seconds()
    return delta

def time_intervals_overlap(t1_start, t1_end, t2_start, t2_end):
    '''
    check if two time intervals overlap
    '''
    delta = time_intervals_overlap_seconds(t1_start, t1_end, t2_start, t2_end)
    return delta > 0

def round_cents(dollars):
    '''
    round dollars to nearest cent
    '''
    cent = Decimal('0.01')
    return Decimal(dollars).quantize(cent, ROUND_HALF_UP)

def get_class_from_name(dotted_path):
    """
    Utility that will return the class object for a fully qualified
    classname
    """
    try:
        module_path, class_name = dotted_path.rsplit('.', 1)
    except ValueError as e:
        msg = "%s doesn't look like a module path" % dotted_path
        raise ImportError(msg) from e

    module = import_module(module_path)

    try:
        return getattr(module, class_name)
    except AttributeError as e:
        msg = 'Module "%s" does not define a "%s" attribute/class' % (
            module_path, class_name)
        raise ImportError(msg) from e
