# -*- coding: utf-8 -*-

'''
Update Products from Fiine
'''
import sys
from django.core.management.base import BaseCommand
from ifxbilling.fiine import updateProducts


class Command(BaseCommand):
    '''
    Update Products using Fiine
    '''
    help = 'Update all Products using Fiine. Usage:\n' + \
        "./manage.py updateProducts"

    def handle(self, *args, **kwargs):
        try:
            updateProducts()
        except Exception as e:
            sys.stderr.write(f'Error updating products from fiine {e}\n')
            exit(1)

        print(f'Products updated.')

