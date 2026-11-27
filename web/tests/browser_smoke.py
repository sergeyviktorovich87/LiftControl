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
import urllib.parse
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))

async def field_check(page,name,company,output):
    from playwright.async_api import expect
    await page.goto(f'http://127.0.0.1:18081/?organization={company}#home')
    await page.get_by_role('heading',name='Главная',exact=True).wait_for()

    response=await page.request.get(f'http://127.0.0.1:18081/?organization={company}')
    await page.goto(f'http://127.0.0.1:18081/?organization={company}#objects')
    assert 'no-store' in response.headers.get('cache-control','')
    await page.get_by_role('heading',name='Объекты',exact=True).wait_for()
    await page.get_by_role('textbox',name='Поиск лифтов').fill('CI-INSPECTION')
    await page.get_by_role('button').filter(has_text='CI-INSPECTION').click()
    card=page.get_by_role('dialog')
    entrance=card.get_by_role('heading',name='Подъезд 1 (Левый)',exact=True)
    await expect(entrance).to_be_visible()
    inventory=card.get_by_text('Учётный номер',exact=True)
    assert (await entrance.bounding_box())['y'] < (await inventory.bounding_box())['y']
    assert await entrance.evaluate("node => parseFloat(getComputedStyle(node).fontSize) >= 22")
    await card.get_by_role('button',name='Освидетельствование',exact=True).click()
    act=card.get_by_role('link',name='Проверочный акт')
    await expect(act).to_be_visible()
    assert await card.get_by_role('button',name=re.compile('Удалить')).count()==0
    pdf=await page.request.get(urllib.parse.urljoin(page.url,await act.get_attribute('href')))
    assert pdf.ok and pdf.headers['content-type']=='application/pdf'
    assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth')
    await card.get_by_role('button', name='Закрыть', exact=True).click()
    if name.startswith('owner'):
        await page.get_by_role('button',name=re.compile('Действия дома:')).first.click()
        await page.get_by_role('menuitem', name='Изменить дом', exact=True).click()
        await expect(card.get_by_role('heading', name='Изменить дом', exact=True)).to_be_visible()
        await card.get_by_role('button', name='Закрыть', exact=True).click()
        await page.get_by_role('button',name='Добавить',exact=True).click()
        await page.get_by_role('menuitem', name='Добавить лифт', exact=True).click()
        await card.get_by_label('Дом', exact=True).fill('Игнатьевское')
        options=await card.locator('datalist option').evaluate_all('(options) => options.map(option => option.value)')
        assert options and all('Игнатьевское' in option for option in options)
        await expect(card.get_by_label('Учётного номера нет', exact=True)).to_be_visible()
        await card.get_by_role('button', name='Закрыть', exact=True).click()
    await page.goto(f'http://127.0.0.1:18081/?organization={company}#home')
    await page.get_by_role('heading',name='Главная',exact=True).wait_for()
    if name.startswith('owner'):
        assert await page.get_by_role('button',name='Запросить подмену',exact=True).count()==0
        await page.goto(f'http://127.0.0.1:18081/?organization={company}#tasks')
        await page.get_by_role('button',name='Новое задание',exact=True).click()
        await page.get_by_role('heading',name='Новое личное задание',exact=True).wait_for()
        await page.get_by_label('Задание',exact=True).fill('Личное поручение '+name)
        await page.get_by_label('Механик',exact=True).select_option(label='Николаи А.')
        await page.get_by_label('Описание',exact=True).fill('Проверить комплект инструмента')
        assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth'),'Task form overflow'
        await page.screenshot(path=str(output/f'{name}-personal-task-form.png'),full_page=True)
        await page.get_by_role('button',name='Назначить задание',exact=True).click()
        await page.get_by_role('heading',name='Новое личное задание',exact=True).wait_for(state='hidden')
        await page.get_by_role('button').filter(has_text='Личное поручение '+name).wait_for()
        await page.goto(f'http://127.0.0.1:18081/?organization={company}#documents')
        docs=page.locator('.documentation')
        await docs.get_by_role('button',name='Новая папка',exact=True).click()
        await page.get_by_label('Название',exact=True).fill('Схемы '+name)
        await page.get_by_label('Теги папки через запятую',exact=True).fill('as380')
        await page.get_by_role('button',name='Сохранить',exact=True).click()
        await docs.locator('.doc-filename').filter(has_text='Схемы '+name).click()
        filename='Схема '+name+'.pdf'
        async with page.expect_response(lambda response: response.url.split('?')[0].endswith('/api/documents/') and response.request.method=='POST') as upload_response:
            await docs.locator('input[type=file]').set_input_files({'name':filename,'mimeType':'application/pdf','buffer':b'%PDF-1.7\nCI document'})
        uploaded=(await (await upload_response.value).json())
        assert (await upload_response.value).status==201, uploaded
        await docs.get_by_role('checkbox',name='Выбрать '+filename,exact=True).check()
        await docs.get_by_role('button',name='Изменить',exact=True).click()
        await page.get_by_role('heading',name='Переименовать документ',exact=True).wait_for()
        await page.get_by_label('Название',exact=True).fill('Схема после правки '+name)
        await page.get_by_role('button',name='Сохранить',exact=True).click()
        edited=docs.locator('.doc-row').filter(has_text='Схема после правки '+name)
        await expect(edited).to_be_visible()
        await docs.get_by_role('checkbox',name='Выбрать Схема после правки '+name,exact=True).check()
        await docs.get_by_role('button',name='Удалить',exact=True).click()
        await page.get_by_role('heading',name='Переместить в корзину',exact=True).wait_for()
        await page.get_by_label('Причина удаления',exact=True).fill('Ошибочно загруженная схема')
        await page.get_by_role('button',name='В корзину',exact=True).click()
        await expect(edited).to_have_count(0)
        assert (await page.request.get(urllib.parse.urljoin(page.url,uploaded['url']))).status==404

        await page.goto(f'http://127.0.0.1:18081/?organization={company}#settings/organizations')
        await expect(page.get_by_text('Категории уведомлений',exact=True)).to_have_count(0)
        if name=='owner-phone':
            await page.goto(f'http://127.0.0.1:18081/?organization={company}#settings/appearance')
            await page.get_by_label('Тема оформления', exact=True).select_option('dark')
    await page.get_by_role('button',name='Открыть чат',exact=True).click()
    await page.get_by_role('heading',name='Чат',exact=True).wait_for()
    await page.get_by_role('textbox',name='Сообщение',exact=True).fill('Фото и видео '+name)
    attachments=[str(output/'fixture.png')]
    if (output/'fixture.mp4').exists():attachments.append(str(output/'fixture.mp4'))
    await page.get_by_label('Прикрепить фото или видео',exact=True).set_input_files(attachments)
    await page.get_by_role('button',name='Отправить',exact=True).click()
    message=page.locator('article.messenger-bubble').filter(has_text='Фото и видео '+name)
    await expect(message.get_by_alt_text('Фото в чате')).to_be_visible()
    if len(attachments)>1:
        await expect(message.locator('video')).to_be_visible()
        await page.wait_for_function("() => [...document.querySelectorAll('video')].every(v=>v.readyState>=1)")
    assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth'),'Chat overflow'
    await page.screenshot(path=str(output/f'{name}-media-chat.png'),full_page=True)
    await page.get_by_role('button',name='Меню чата',exact=True).click()
    await page.get_by_role('button',name='Вложения чата',exact=True).click()
    library=page.locator('.media-library')
    await expect(library.locator('.media-card').first).to_be_visible()
    await expect(library.get_by_role('link',name='Исходное сообщение').first).to_be_visible()
    assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth'),'Media library overflow'
    before=await library.locator('.media-card').count()
    await library.get_by_label('Тип файла',exact=True).select_option('image')
    await library.get_by_role('button',name='Показать',exact=True).click()
    await expect(library.locator('video')).to_have_count(0)
    await expect(library.locator('.media-card').first).to_be_visible()
    await page.screenshot(path=str(output/f'{name}-media-library.png'),full_page=True)

    if name=='worker':
        await page.goto(f'http://127.0.0.1:18081/?organization={company}#tasks')
        await page.get_by_role('heading',name='Личные задания',exact=True).wait_for()
        assert await page.get_by_role('button',name='Новое задание',exact=True).count()==0
        await page.get_by_role('button').filter(has_text='Личное поручение owner-phone').click()
        await page.get_by_role('button',name='Принять задание',exact=True).click()
        await page.get_by_role('button',name='Завершить с отчётом',exact=True).click()
        await page.get_by_label('Что выполнено',exact=True).fill('Работа выполнена в браузере')
        await page.get_by_role('button',name='Завершить',exact=True).click()
        await expect(page.get_by_text('Работа выполнена в браузере',exact=True).first).to_be_visible()

async def check(sessions,company,everest,output):
    from playwright.async_api import async_playwright, expect
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True, **({'executable_path':os.environ['LIFTCONTROL_CHROMIUM_PATH']} if os.environ.get('LIFTCONTROL_CHROMIUM_PATH') else {}))
        compression=await browser.new_page()
        modules = {'compression-module.js': 'imageCompression.js', 'uploadLimits.js': 'uploadLimits.js'}
        await compression.route(
            re.compile(r'/(?:compression-module|uploadLimits)\.js$'),
            lambda route: route.fulfill(
                content_type='text/javascript',
                body=(ROOT/'web/src'/modules[Path(route.request.url).name]).read_text(),
            ),
        )
        await compression.goto('http://127.0.0.1:18081/api/health/')
        metrics=await compression.evaluate('''async () => {
          const {compressImage}=await import('/compression-module.js');
          const small=new File(['tiny'],'small.jpg',{type:'image/jpeg'});
          if(await compressImage(small)!==small)throw Error('Small image was re-encoded');
          const video=new File(['video'],'clip.mp4',{type:'video/mp4'});
          if(await compressImage(video)!==video)throw Error('Video was changed');
          const canvas=document.createElement('canvas');canvas.width=4032;canvas.height=3024;
          const ctx=canvas.getContext('2d'),image=ctx.createImageData(canvas.width,canvas.height);
          let seed=7;for(let i=0;i<image.data.length;i+=4){seed=(seed*1664525+1013904223)>>>0;image.data[i]=seed&255;image.data[i+1]=(seed>>>8)&255;image.data[i+2]=(seed>>>16)&255;image.data[i+3]=255;}
          ctx.putImageData(image,0,0);
          const source=new File([await new Promise(r=>canvas.toBlob(r,'image/jpeg',.92))],'photo.jpg',{type:'image/jpeg'});
          const start=performance.now(),result=await compressImage(source),ms=performance.now()-start;
          const bitmap=await createImageBitmap(result),dims=[bitmap.width,bitmap.height];bitmap.close();
          if(result.size>=source.size*.5||Math.max(...dims)>1920||result.type!=='image/jpeg')throw Error('Compression did not reduce photo');
          return {input:source.size,output:result.size,ms:Math.round(ms),dimensions:dims};
        }''')
        print('IMAGE_COMPRESSION_VERIFIED',metrics,flush=True)
        await compression.close()
        off=await browser.new_context(viewport={'width':320,'height':720})
        await off.add_cookies([{'name':'sessionid','value':sessions['off-duty'],'url':'http://127.0.0.1:18081','httpOnly':True,'sameSite':'Lax'}])
        off_page=await off.new_page()
        await off_page.goto(f'http://127.0.0.1:18081/?organization={company}#home')
        await off_page.get_by_role('heading',name='Главная',exact=True).wait_for()
        await expect(off_page.locator('.topbar-duty')).to_have_attribute('aria-label','Дежурный: Николаи А.')
        assert await off_page.get_by_role('button',name='Запросить подмену',exact=True).count()==0
        assert await off_page.locator('.duty-status').count()==0
        assert not await off_page.evaluate('document.documentElement.scrollWidth > innerWidth'),'Off duty phone overflow'
        await off_page.goto(f'http://127.0.0.1:18081/?organization={company}#duty')
        await off_page.get_by_role('heading',name='Дежурства',exact=True).wait_for()
        assert await off_page.get_by_role('button',name='Запросить подмену',exact=True).count()==0
        await off.close()
        errors=[]
        for name,viewport in [('owner',{'width':1440,'height':1000}),('owner-phone',{'width':390,'height':844}),('worker',{'width':390,'height':844})]:
            context=await browser.new_context(viewport=viewport)
            await context.add_cookies([{'name':'sessionid','value':sessions['owner' if name.startswith('owner') else 'worker'],'url':'http://127.0.0.1:18081','httpOnly':True,'sameSite':'Lax'}])
            page=await context.new_page()
            page.on('pageerror',lambda e:errors.append(str(e)))
            try:
                await page.goto(f'http://127.0.0.1:18081/?organization={company}#home')
                await page.get_by_role('heading',name='Главная',exact=True).wait_for()
                await expect(page.locator('.topbar-duty')).to_have_attribute('aria-label','Дежурный: Николаи А.')
                assert await page.locator('.topbar .global-search, .topbar .mode-label, .topbar .top-profile').count()==0
                assert await page.get_by_role('button',name='Запросить подмену',exact=True).count()==(1 if name=='worker' else 0)
                assert await page.locator('.home-workspace .metrics').count()==0
                assert await page.get_by_role('button',name='Мои',exact=True).count()==(1 if name=='worker' else 0)
                if name=='worker':
                    await page.get_by_role('button',name='Принял смену',exact=True).click()
                    await page.get_by_text('Выход на связь подтверждён',exact=False).wait_for()
                    await expect(page.locator('.topbar-duty .duty-acceptance')).to_have_class(re.compile('accepted'))
                    assert await page.get_by_role('button',name='Новая заявка',exact=True).count()==1
                assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth'),'Home overflow'
                await page.goto(f'http://127.0.0.1:18081/?organization={company}#duty')
                await page.get_by_role('heading', name='Дежурства', exact=True).wait_for()
                current_duty=page.locator('.duty-status')
                await expect(current_duty).to_have_count(1)
                await current_duty.get_by_text('Дежурный: Николаи А.', exact=True).wait_for()
                current_node=await current_duty.element_handle()
                async with page.expect_response(lambda response: response.url.endswith('/api/me/')):
                    await page.evaluate("window.dispatchEvent(new Event('focus'))")
                assert await current_node.evaluate('(node) => node.isConnected')
                await expect(current_duty).to_have_count(1)
                assert await page.get_by_role('dialog').count()==0
                await page.locator('.roster-cell').first.click()
                await page.locator('.roster-details').wait_for()
                assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth'),'Duty overflow'
                assert await page.locator('.roster-panel').get_by_role('button',name='Открыть',exact=True).count()==0
                if name.startswith('owner'):
                    await page.get_by_role('button',name='Следующий месяц',exact=True).click()
                    await page.locator('.roster-cell').first.wait_for()
                    await page.get_by_role('button',name='Проверить и опубликовать',exact=True).click()
                    await page.get_by_role('button',name='Проверить даты',exact=True).click()
                    await page.get_by_text('Назначьте дежурных на даты',exact=False).wait_for()
                    assert await page.get_by_role('button',name='Опубликовать',exact=True).count()==0
                await page.goto(f'http://127.0.0.1:18081/?organization={company}#settings/organizations')
                await page.get_by_role('heading',name='Организации',exact=True).wait_for()
                assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth'),'Settings overflow'
                if name.startswith('owner'):
                    await page.goto(f'http://127.0.0.1:18081/?organization={company}#technicians')
                    await page.get_by_role('button',name='Добавить сотрудника',exact=True).click()
                    await page.get_by_role('heading',name='Добавить сотрудника',exact=True).wait_for()
                    assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth'),'Employee form overflow'
                    assert await page.evaluate('''() => {const controls=[...document.querySelectorAll('#employee-create input,#employee-create select,#employee-create button')].map(e=>e.getBoundingClientRect());return controls.every((a,i)=>controls.every((b,j)=>i===j||a.right<=b.left+1||b.right<=a.left+1||a.bottom<=b.top+1||b.bottom<=a.top+1));}'''),'Employee controls overlap'
                    await page.get_by_label('ФИО сотрудника',exact=True).fill('Проверка добавления '+name)
                    username='qa_new_worker_'+name.replace('-','_')
                    await page.get_by_label('Логин',exact=True).fill(username)
                    await page.get_by_role('button',name='Создать сотрудника и ссылку',exact=True).click()
                    link_notice=page.locator('#employee-create .notice')
                    await expect(link_notice.get_by_role('button',name='Копировать ссылку')).to_be_visible()
                    link=await link_notice.locator('code').inner_text()
                    employee_context=await browser.new_context(viewport=viewport)
                    try:
                        employee=await employee_context.new_page()
                        await employee.goto(link)
                        await expect(employee.get_by_label('Новый пароль',exact=True)).to_be_visible()
                        assert not await employee.evaluate('document.documentElement.scrollWidth > innerWidth'),'Password setup overflow'
                        password='UniqueBrowserTestPassword-2026!'
                        await employee.get_by_label('Новый пароль',exact=True).fill(password)
                        await employee.get_by_label('Повторите пароль',exact=True).fill(password)
                        await employee.get_by_role('button',name='Сохранить пароль',exact=True).click()
                        await expect(employee.get_by_text('Пароль установлен.',exact=True)).to_be_visible()
                        await employee.get_by_role('link',name='Войти в веб-панель').click()
                        await employee.get_by_label('Логин',exact=True).fill(username)
                        await employee.get_by_label('Пароль',exact=True).fill(password)
                        await employee.get_by_role('button',name='Войти',exact=True).click()
                        await expect(employee.get_by_role('heading',name='Главная',exact=True)).to_be_visible()
                    finally:
                        await employee_context.close()
                    await page.goto(f'http://127.0.0.1:18081/?organization={company}#technicians')
                    await page.locator('.staff-row').get_by_text('Проверка добавления '+name,exact=True).wait_for()
                    await field_check(page,name,company,output)
                else:
                    assert await page.get_by_role('button',name='Создать код',exact=True).count()==0
                    await field_check(page,name,company,output)
                    await page.goto(f'http://127.0.0.1:18081/?organization={company}#settings/organizations')
                    await page.get_by_role('heading',name='Организации',exact=True).wait_for()
                    await page.get_by_role('button',name='ООО «Эверест» · Механик',exact=True).click()
                    await page.get_by_role('heading',name='Главная',exact=True).wait_for()
                    assert await page.get_by_role('button',name='Новая заявка',exact=True).count()==0
                    await page.get_by_role('heading',name='Активных заявок нет',exact=True).wait_for()
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
        os.environ['DJANGO_MEDIA_ROOT']=str(Path(temp)/'media')
        os.environ['DJANGO_SETTINGS_MODULE']='liftcontrol.settings'
        import django
        django.setup()
        from django.core.management import call_command
        from django.contrib.auth import get_user_model
        from django.test import Client
        from django.utils import timezone
        from datetime import timedelta
        from django.core.files.base import ContentFile
        from core.models import Organization,Membership,Technician,DutyShift,Elevator,LiftDocument
        call_command('migrate',verbosity=0)
        call_command('import_megapolis',apply=True,replace_work_data=True,backup=str(Path(temp)/'before.json'),verbosity=0)
        company=Organization.objects.get(name='Мегаполис')
        everest=Organization.objects.get(name='ООО «Эверест»')
        owner=get_user_model().objects.create_superuser(username='qa_owner')
        worker=get_user_model().objects.create_user(username='qa_worker',first_name='Тестовый механик')
        tech=Technician.objects.get(organization=company,full_name='Николаи А.')
        lift=Elevator.objects.filter(organization=company,active=True).first()
        lift.inventory_number='CI-INSPECTION'
        lift.entrance='1 (Левый)'
        lift.save(update_fields=['inventory_number','entrance'])
        act=LiftDocument(organization=company,elevator=lift,category='INSPECTION',title='Проверочный акт')
        act.file.save('inspection.pdf',ContentFile(b'%PDF-1.7\nCI inspection'))
        othertech=Technician.objects.create(organization=everest,full_name='Совместитель (проверка)')
        for o in (company,everest):Membership.objects.create(user=owner,organization=o,role='ADMIN')
        for o,t in [(company,tech),(everest,othertech)]:Membership.objects.create(user=worker,organization=o,role='MECHANIC',technician=t)
        now=timezone.now()
        DutyShift.objects.create(organization=company,technician=tech,start=now-timedelta(hours=1),end=now+timedelta(hours=23))
        off_user=get_user_model().objects.create_user(username='qa_off_duty')
        off_tech=Technician.objects.filter(organization=company,role='MECHANIC',active=True).exclude(pk=tech.pk).first()
        assert off_tech is not None
        Membership.objects.create(user=off_user,organization=company,role='MECHANIC',technician=off_tech)
        DutyShift.objects.create(organization=company,technician=off_tech,start=now+timedelta(hours=23),end=now+timedelta(hours=47))
        sessions={}
        for name,u in [('owner',owner),('worker',worker),('off-duty',off_user)]:
            client=Client();client.force_login(u);sessions[name]=client.cookies['sessionid'].value
        output=ROOT/'browser-test-output'
        output.mkdir(exist_ok=True)
        Image.new('RGB',(16,16),'green').save(output/'fixture.png')
        import shutil
        if shutil.which('ffmpeg'):
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=green:s=16x16:d=1',
                '-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(output/'fixture.mp4')],check=True,timeout=15)
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
