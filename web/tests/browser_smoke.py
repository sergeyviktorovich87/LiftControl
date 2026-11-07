"""Browser integration check in a fresh disposable SQLite database, never production."""
import asyncio
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))

async def check(sessions,company,everest,output):
    from playwright.async_api import async_playwright, expect
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True, **({'executable_path':os.environ['LIFTCONTROL_CHROMIUM_PATH']} if os.environ.get('LIFTCONTROL_CHROMIUM_PATH') else {}))
        errors=[]
        for name,viewport in [('owner',{'width':1440,'height':1000}),('worker',{'width':390,'height':844})]:
            context=await browser.new_context(viewport=viewport)
            await context.add_cookies([{'name':'sessionid','value':sessions[name],'url':'http://127.0.0.1:18081','httpOnly':True,'sameSite':'Lax'}])
            page=await context.new_page()
            page.on('pageerror',lambda e:errors.append(str(e)))
            try:
                await page.goto(f'http://127.0.0.1:18081/?organization={company}#home')
                await page.get_by_role('heading',name='Главная',exact=True).wait_for()
                assert await page.get_by_text('Дежурный: Николаи А.',exact=True).count()==1
                await expect(page.get_by_role('button',name=re.compile('Лифтов на обслуживании')).locator('strong')).to_have_text('157')
                if name=='worker':
                    await page.get_by_role('button',name='Принял смену',exact=True).click()
                    await page.get_by_text('Выход на связь подтверждён',exact=False).wait_for()
                    assert await page.get_by_role('button',name='Новая заявка',exact=True).count()==1
                assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth'),'Home overflow'
                await page.goto(f'http://127.0.0.1:18081/?organization={company}#settings')
                await page.get_by_role('heading',name='Настройки',exact=True).wait_for()
                await page.get_by_role('heading',name='Организации',exact=True).wait_for()
                assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth'),'Settings overflow'
                if name=='owner':
                    await page.goto(f'http://127.0.0.1:18081/?organization={company}#technicians')
                    await page.get_by_role('button',name='Добавить сотрудника',exact=True).click()
                    await page.get_by_role('heading',name='Добавить сотрудника',exact=True).wait_for()
                    await page.get_by_label('ФИО сотрудника',exact=True).fill('Проверка добавления')
                    await page.get_by_label('Логин',exact=True).fill('qa_new_worker')
                    await page.get_by_label('Пароль (от 12 символов)',exact=True).fill('UniqueBrowserTestPassword-2026!')
                    await page.get_by_role('button',name='Создать сотрудника и доступ',exact=True).click()
                    await page.get_by_role('status').filter(has_text='Сотрудник и учётная запись созданы').wait_for()
                    await page.goto(f'http://127.0.0.1:18081/?organization={company}#technicians')
                    await page.get_by_role('heading',name='Проверка добавления',exact=True).wait_for()
                else:
                    assert await page.get_by_role('button',name='Создать код',exact=True).count()==0
                    await page.get_by_role('button',name='ООО «Эверест» · Механик',exact=True).click()
                    await page.get_by_role('heading',name='Главная',exact=True).wait_for()
                    assert await page.get_by_role('button',name='Новая заявка',exact=True).count()==0
                    await expect(page.get_by_role('button',name=re.compile('Лифтов на обслуживании')).locator('strong')).to_have_text('0')
                print(name+': browser integration passed, no horizontal overflow')
            except Exception:
                await page.screenshot(path=str(output/f'failed-{name}.png'),full_page=True)
                raise
            finally:
                await context.close()
        assert not errors,errors
        await browser.close()


def main():
    with tempfile.TemporaryDirectory(prefix='liftcontrol-browser-') as temp:
        os.environ['DJANGO_DEBUG']='True'
        os.environ['DB_ENGINE']='sqlite'
        os.environ['DJANGO_SQLITE_PATH']=str(Path(temp)/'browser.sqlite3')
        os.environ['DJANGO_SETTINGS_MODULE']='liftcontrol.settings'
        import django
        django.setup()
        from django.core.management import call_command
        from django.contrib.auth import get_user_model
        from django.test import Client
        from django.utils import timezone
        from datetime import timedelta
        from core.models import Organization,Membership,Technician,DutyShift
        call_command('migrate',verbosity=0)
        call_command('import_megapolis',apply=True,replace_work_data=True,backup=str(Path(temp)/'before.json'),verbosity=0)
        company=Organization.objects.get(name='Мегаполис')
        everest=Organization.objects.get(name='ООО «Эверест»')
        owner=get_user_model().objects.create_superuser(username='qa_owner')
        worker=get_user_model().objects.create_user(username='qa_worker',first_name='Тестовый механик')
        tech=Technician.objects.get(organization=company,full_name='Николаи А.')
        othertech=Technician.objects.create(organization=everest,full_name='Совместитель (проверка)')
        for o in (company,everest):Membership.objects.create(user=owner,organization=o,role='ADMIN')
        for o,t in [(company,tech),(everest,othertech)]:Membership.objects.create(user=worker,organization=o,role='MECHANIC',technician=t)
        now=timezone.now()
        DutyShift.objects.create(organization=company,technician=tech,start=now-timedelta(hours=1),end=now+timedelta(hours=23))
        sessions={}
        for name,u in [('owner',owner),('worker',worker)]:
            client=Client();client.force_login(u);sessions[name]=client.cookies['sessionid'].value
        output=ROOT/'browser-test-output'
        output.mkdir(exist_ok=True)
        log=(output/'server.log').open('w')
        server=subprocess.Popen([sys.executable,'manage.py','runserver','127.0.0.1:18081','--noreload'],cwd=ROOT/'backend',env=os.environ,stdout=log,stderr=subprocess.STDOUT)
        try:
            for attempt in range(60):
                if server.poll() is not None:raise RuntimeError('Django development server failed')
                try:
                    urllib.request.urlopen('http://127.0.0.1:18081/api/health/',timeout=1).close()
                    break
                except OSError:time.sleep(.25)
            else:raise RuntimeError('Django startup timeout')
            asyncio.run(check(sessions,company.pk,everest.pk,output))
        finally:
            server.terminate()
            server.wait(timeout=10)
            log.close()
if __name__=='__main__':main()
