# -*- coding: utf-8 -*-

'''
Calculate billing records for the given year and month
'''
import logging
import re
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.core.management import call_command
from ifxbilling.calculator import calculateMonth


logger = logging.getLogger('ifxbilling')


class Command(BaseCommand):
    '''
    Calculate billing records for the given year and month
    '''
    help = 'Calculate billing records for the given year and month.  Use --recalculate to remove existing records and recreate. Usage:\n' + \
        "./manage.py calculateBillingRecords --year 2021 --month 3"

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            dest='year',
            default=timezone.now().year,
            help='Year for calculation',
        )
        parser.add_argument(
            '--month',
            dest='month',
            default=timezone.now().month,
            help='Month for calculation',
        )
        parser.add_argument(
            '--recalculate',
            action='store_true',
            help='Remove existing billing records and recalculate',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Report full exception for errors',
        )

    def handle(self, *args, **kwargs):
        month = int(kwargs['month'])
        year = int(kwargs['year'])
        recalculate = kwargs['recalculate']
        verbose = kwargs['verbose']

        (successes, errors) = calculateMonth(month, year, recalculate, verbose)

        print(f'{successes} product usages successfully processed')
        if errors:
            print('Errors: %s' % '\n'.join(errors))
