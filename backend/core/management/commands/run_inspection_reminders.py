import logging
import time

from django.core.management.base import BaseCommand

from core.inspection_reminders import enqueue_due_inspections

logger = logging.getLogger('liftcontrol.push')


class Command(BaseCommand):
    help = 'Queue daily reminders for scheduled lift inspections.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        while True:
            try:
                count = enqueue_due_inspections()
                if count:
                    logger.info('inspection_reminders_queued count=%s', count)
            except Exception as error:
                if options['once']:
                    raise
                logger.warning('inspection_reminders_failed error=%s', type(error).__name__)
            if options['once']:
                return
            time.sleep(60)
