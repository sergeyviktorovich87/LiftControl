from tempfile import TemporaryDirectory
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from .tests_lift_documents import LiftDocumentTests
from .models import Elevator, LiftDocument, LiftDocumentFolder


class LiftDocumentFolderTests(TestCase):
    setUp = LiftDocumentTests.setUp
    sign_in = LiftDocumentTests.sign_in
    upload = LiftDocumentTests.upload

    def setUp(self):
        LiftDocumentTests.setUp(self)
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        setting = override_settings(MEDIA_ROOT=self.media.name)
        setting.enable(); self.addCleanup(setting.disable)
        self.sign_in(self.admin)
        self.second = Elevator.objects.create(organization=self.company, building=self.lift.building, entrance='2')

    def action(self, action, **body):
        return self.client.post('/api/lift-document-folders/', {'action':action, **body}, format='json')

    def folder(self, name='Ленина, 12', **body):
        response=self.action('create',name=name,**body)
        self.assertEqual(response.status_code,200,response.data)
        return response.data

    def attach_pdf(self, folder, category='CONTRACT'):
        response=self.client.post('/api/lift-documents/', {'folder':folder,'category':category,'title':'Акт.pdf',
            'file':SimpleUploadedFile('act.pdf',b'%PDF-1.7\nfixture',content_type='application/pdf')},format='multipart')
        self.assertEqual(response.status_code,201,response.data)
        return response.data

    def card(self, lift):
        return self.client.get('/api/lift-document-folders/',{'elevator':lift.pk})

    def test_multiple_lifts_inherit_and_unlink_revokes_file_access(self):
        root=self.folder(elevator_ids=[self.lift.pk,self.second.pk])
        child=self.folder('Освидетельствование',parent_id=root['id'])
        pdf=self.attach_pdf(child['id'],'INSPECTION')
        self.sign_in(self.mechanic)
        for lift in [self.lift,self.second]:
            card=self.card(lift)
            self.assertEqual([d['id'] for d in card.data['documents']],[pdf['id']])
        self.assertEqual(self.client.get(pdf['url']).status_code,200)
        self.assertEqual(self.client.get(f'/api/lift-inspections/{self.second.pk}/').data['acts'][0]['id'],pdf['id'])
        self.assertEqual(self.action('edit',id=root['id'],name='X',elevator_ids=[]).status_code,403)
        self.sign_in(self.admin)
        self.assertEqual(self.action('edit',id=root['id'],elevator_ids=[]).status_code,200)
        self.sign_in(self.mechanic)
        self.assertEqual(self.card(self.lift).data['documents'],[])
        self.assertEqual(self.client.get(pdf['url']).status_code,404)

    def test_legacy_privacy_preserved_until_explicit_move_to_shared_folder(self):
        contract=self.upload('CONTRACT').data
        act=self.upload('INSPECTION').data
        root=self.folder(elevator_ids=[self.lift.pk])
        self.sign_in(self.mechanic)
        self.assertEqual(self.client.get(contract['url']).status_code,404)
        self.assertEqual([d['id'] for d in self.card(self.lift).data['documents']],[act['id']])
        self.sign_in(self.admin)
        self.assertEqual(self.action('move',documents=[contract['id']],target=root['id']).status_code,200)
        self.sign_in(self.mechanic)
        self.assertEqual(self.client.get(contract['url']).status_code,200)
        self.assertEqual(set(d['id'] for d in self.card(self.lift).data['documents']),{contract['id'],act['id']})

    def test_foreign_objects_and_identifiers_cannot_be_linked_or_mutated(self):
        foreign=Elevator.objects.create(organization=self.foreign, building=self.lift.building)
        self.assertEqual(self.action('create',name='Bad',elevator_ids=[foreign.pk]).status_code,400)
        foreign_folder=LiftDocumentFolder.objects.create(organization=self.foreign,name='Private')
        self.assertEqual(self.action('create',name='Bad',parent_id=foreign_folder.pk).status_code,404)
        self.assertEqual(self.action('delete',folders=[foreign_folder.pk],reason='Test deletion').status_code,400)
        self.assertEqual(self.card(foreign).status_code,404)
        for ids in [[True],['1'],[0],[-1]]:
            self.assertEqual(self.action('create',name='Bad',elevator_ids=ids).status_code,400)

    def test_cycles_copy_move_and_own_bindings(self):
        root=self.folder(elevator_ids=[self.lift.pk]); child=self.folder('Child',parent_id=root['id'],elevator_ids=[self.second.pk])
        pdf=self.attach_pdf(child['id'])
        self.assertEqual(self.action('move',folders=[root['id']],target=child['id']).status_code,400)
        self.assertEqual(self.action('edit',id=root['id'],parent_id=child['id']).status_code,400)
        self.assertEqual(self.action('copy',folders=[root['id']],target=None).status_code,200)
        self.assertEqual(LiftDocument.objects.filter(file=LiftDocument.objects.get(pk=pdf['id']).file.name).count(),2)
        copied=LiftDocumentFolder.objects.get(name='Ленина, 12 — копия')
        self.assertEqual(list(copied.elevators.values_list('pk',flat=True)),[self.lift.pk])
        self.assertEqual(self.action('move',folders=[child['id']],target=None).status_code,200)
        self.sign_in(self.mechanic)
        self.assertNotIn(pdf['id'],[d['id'] for d in self.card(self.lift).data['documents']])
        self.assertIn(pdf['id'],[d['id'] for d in self.card(self.second).data['documents']])

    def test_trash_restore_preserves_files_and_previous_deletion_batches(self):
        root=self.folder(elevator_ids=[self.lift.pk]); child=self.folder('Child',parent_id=root['id'])
        pdf=self.attach_pdf(child['id']); older=self.attach_pdf(root['id'])
        self.assertEqual(self.action('delete',documents=[older['id']],reason='Old deletion').status_code,200)
        self.assertEqual(self.action('delete',folders=[root['id']],reason='Delete tree').status_code,200)
        self.assertEqual(self.client.get(pdf['url']).status_code,404)
        self.assertTrue(LiftDocument.objects.get(pk=pdf['id']).file.storage.exists(LiftDocument.objects.get(pk=pdf['id']).file.name))
        self.assertEqual(self.action('restore',folders=[child['id']]).status_code,400)
        self.assertEqual(self.action('restore',folders=[root['id']]).status_code,200)
        self.assertEqual(self.client.get(pdf['url']).status_code,200)
        self.assertIsNotNone(LiftDocument.objects.get(pk=older['id']).deleted_at)

    def test_upload_and_rename_require_admin_and_current_revision(self):
        root=self.folder(); pdf=self.attach_pdf(root['id'])
        path=f"/api/lift-documents/{pdf['id']}/"
        self.assertEqual(self.client.patch(path,{'title':'New','expected_updated_at':pdf['updated_at']},format='json').status_code,200)
        self.assertEqual(self.client.patch(path,{'title':'Stale','expected_updated_at':pdf['updated_at']},format='json').status_code,400)
        self.sign_in(self.director)
        self.assertEqual(self.client.get('/api/lift-document-folders/').status_code,403)
        self.assertEqual(self.client.patch(path,{'title':'Forbidden','expected_updated_at':pdf['updated_at']},format='json').status_code,403)
        self.assertEqual(self.client.get(pdf['url']).status_code,404)
