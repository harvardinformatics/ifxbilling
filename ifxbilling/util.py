# -*- coding: utf-8 -*-

'''
utility functions

Created on  2021-10-01

@author: Meghan Correa <mportermahoney@g.harvard.edu>
@copyright: 2021 The President and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from importlib import import_module

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
