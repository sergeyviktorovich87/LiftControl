"""Small PostgreSQL-backed WebPush worker; run as an isolated container, never as an API thread."""
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from django.db import connections, close_old_connections
from django.core.management.base import BaseCommand
from core.planning_push import process_batch as process_planning_batch
from core.push_notifications import process_batch, push_config
from core.native_push import enabled, process_native_batch
from core.task_push import process_task_batch
from core.commissioning_push import process_commissioning_batch
from core.app_update_push import announce_latest, process_batch as process_update_batch


class Command(BaseCommand):
    help = 'Deliver pending LiftControl push notifications from durable queue.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--interval', type=int, default=2)

    def handle(self, *args, **options):
        if not push_config()['enabled'] and not enabled():
            self.stdout.write('WEBPUSH_DISABLED: VAPID key and subject are not configured')
            return
        interval = max(1, min(60, options['interval']))
        last_release_scan = None
        self.stdout.write('LIFTCONTROL_PUSH_WORKER_STARTED')
        queues = [('tickets',process_batch),('inbox',process_planning_batch),('native',process_native_batch),('tasks',process_task_batch),('commissioning',process_commissioning_batch),('updates',process_update_batch)]

        def run_queue(name, process, parallel=False):
            if parallel:close_old_connections()
            started=time.monotonic()
            try:
                if name in ('tickets','inbox','tasks'):
                    processed=process(parallel=parallel)
                else:processed=process()
                if isinstance(processed,int) and processed>0:
                    self.stdout.write('PUSH_BATCH channel='+name+' processed='+str(processed)+' elapsed_ms='+str(int((time.monotonic()-started)*1000)))
                return processed
            except Exception as exc:
                self.stderr.write('PUSH_QUEUE_ERROR channel='+name+' error='+type(exc).__name__)
                return 0
            finally:
                if parallel:connections.close_all()

        if options['once']:
            for name,process in queues:run_queue(name,process)
            return

        # Every queue has its own lane. A slow provider cannot hold up other queues.
        # Browser sends use one shared four-thread pool across all lanes.
        pending = {}
        due = {name:0 for name,_ in queues}
        with ThreadPoolExecutor(max_workers=len(queues),thread_name_prefix='push-queue') as lanes:
            while True:
                now = time.monotonic()
                if enabled() and (last_release_scan is None or now-last_release_scan>=60):
                    last_release_scan=now
                    try:announce_latest()
                    except Exception as exc:self.stderr.write('PUSH_RELEASE_SCAN_ERROR: '+type(exc).__name__)
                for name,process in queues:
                    if name not in pending and due[name]<=now:
                        pending[name]=lanes.submit(run_queue,name,process,True)
                done,_=wait(list(pending.values()),timeout=interval,return_when=FIRST_COMPLETED) if pending else (set(),set())
                for name,future in list(pending.items()):
                    if future in done:
                        processed=future.result()
                        # Drain a full batch immediately; idle queues still back off.
                        due[name]=time.monotonic()+(0 if isinstance(processed,int) and processed>=20 else interval)
                        del pending[name]
                if not pending:time.sleep(min(interval,max(0,min(due.values())-time.monotonic())))
