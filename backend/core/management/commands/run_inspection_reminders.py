import logging
import time

from django.core.management.base import BaseCommand

from core.inspection_reminders import enqueue_due_inspections
from core.ticket_delivery import enqueue_due_receipt_warnings

logger = logging.getLogger('liftcontrol.push')


class Command(BaseCommand):
    help = 'Queue inspection reminders and check ticket delivery.'

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
            try:
                count = enqueue_due_receipt_warnings()
                if count:
                    logger.info('ticket_delivery_checks count=%s', count)
            except Exception as error:
                if options['once']:
                    raise
                logger.warning('ticket_delivery_check_failed error=%s', type(error).__name__)
            if options['once']:
                return
            time.sleep(15)
