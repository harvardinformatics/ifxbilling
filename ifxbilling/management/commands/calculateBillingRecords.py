# -*- coding: utf-8 -*-

'''
Calculate billing records for the given year and month
'''
import logging
from django.utils import timezone
from django.core.management.base import BaseCommand
from ifxbilling.calculator import calculateBillingMonth
from ifxbilling.models import Facility


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
        parser.add_argument(
            '--facility-name',
            dest='facility_name',
            help='Name of the facility to calculate for.  Can be omitted if there is only one Facility record.'
        )

    def handle(self, *args, **kwargs):
        month = int(kwargs['month'])
        year = int(kwargs['year'])
        recalculate = kwargs['recalculate']
        verbose = kwargs['verbose']
        facility_name = kwargs.get('facility_name')
        if facility_name:
            try:
                facility = Facility.objects.get(name=facility_name)
            except Facility.DoesNotExist:
                raise Exception(f'Facility name {facility_name} cannot be found')
        else:
            if Facility.objects.all().count() != 1:
                raise Exception('If --facility-name is omitted, there must be exactly one Facility record.')
            facility = Facility.objects.first()

        (successes, errors) = calculateBillingMonth(month, year, facility=facility, recalculate=recalculate, verbose=verbose)

        print(f'{successes} product usages successfully processed')
        if errors:
            print('Errors: %s' % '\n'.join(errors))
