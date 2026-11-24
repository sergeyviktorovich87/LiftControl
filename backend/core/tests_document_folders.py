import tempfile
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from .models import Organization, Membership, Building, Elevator, Technician, DocumentFolder, Document


class DocumentExplorerTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings = override_settings(MEDIA_ROOT=self.media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.org = Organization.objects.get(pk=1)
        self.other = Organization.objects.create(name='Other')
        self.admin = get_user_model().objects.create_user('folder-admin')
        Membership.objects.create(user=self.admin, organization=self.org, role='ADMIN')
        self.worker = get_user_model().objects.create_user('folder-worker')
        tech = Technician.objects.create(organization=self.org, full_name='Worker')
        Membership.objects.create(user=self.worker, organization=self.org, role='MECHANIC', technician=tech)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        building = Building.objects.create(organization=self.org, address='Test', name='Test')
        self.lift = Elevator.objects.create(organization=self.org, building=building, documentation_tags='МЭЛ, Monarch, test')

    def action(self, action, **values):
        return self.client.post('/api/document-folders/', {'action': action, **values}, format='json')

    def folder(self, name='Folder', **values):
        response = self.action('create', name=name, **values)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()['id']

    def doc(self, folder):
        response = self.client.post('/api/documents/', {'title':'Scheme.pdf', 'folder':folder,
            'file':SimpleUploadedFile('scheme.pdf', b'%PDF-1.4\ntest', content_type='application/pdf')}, format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()['id']

    def test_nested_tag_folder_matches_card_and_move_preserves_file(self):
        folder = self.folder(documentation_tags=' мэл, MONARCH ')
        child = self.folder('Nested', parent_id=folder)
        doc = self.doc(child)
        self.assertEqual([d['id'] for d in self.client.get(f'/api/elevators/{self.lift.pk}/documents/').json()], [doc])
        # All required tags must match, not substrings or a single tag.
        self.lift.documentation_tags = 'мэл, monarch-plus'
        self.lift.save()
        self.assertEqual(self.client.get(f'/api/elevators/{self.lift.pk}/documents/').json(), [])
        bound = self.folder('Bound', elevator_id=self.lift.pk)
        self.assertEqual(self.action('move', folders=[child], target=bound).status_code, 200)
        self.assertEqual([d['id'] for d in self.client.get(f'/api/elevators/{self.lift.pk}/documents/').json()], [doc])
        download = self.client.get(f'/api/documents/{doc}/download/')
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b''.join(download.streaming_content), b'%PDF-1.4\ntest')

    def test_cycle_cross_tenant_and_worker_mutations_rejected(self):
        root = self.folder()
        child = self.folder('Child', parent_id=root)
        self.assertEqual(self.action('move', folders=[root], target=child).status_code, 400)
        self.assertEqual(self.action('edit', id=root, name='Root', parent_id=child).status_code, 400)
        foreign = DocumentFolder.objects.create(organization=self.other, name='Foreign')
        self.assertEqual(self.action('move', folders=[root], target=foreign.pk).status_code, 404)
        self.assertEqual(self.action('copy', folders=[foreign.pk]).status_code, 400)
        doc = self.doc(root)
        self.assertEqual(self.client.patch(f'/api/documents/{doc}/', {'folder':foreign.pk}, format='json').status_code, 400)
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.get('/api/document-folders/').status_code, 200)
        self.assertEqual(self.action('create', name='Denied').status_code, 403)
        self.assertEqual(self.action('delete', folders=[root], reason='Denied').status_code, 403)
        self.assertEqual(self.client.get('/api/document-folders/?trash=1').status_code, 403)

    def test_recursive_copy_trash_restore_keeps_older_trash(self):
        root = self.folder()
        child = self.folder('Child', parent_id=root)
        old = self.doc(child)
        self.assertEqual(self.action('delete', documents=[old], reason='Old deleted document').status_code, 200)
        doc = self.doc(child)
        target = self.folder('Target')
        self.assertEqual(self.action('copy', folders=[root], documents=[doc], target=target).status_code, 200)
        # Selected file contained in selected folder is copied exactly once.
        copied_root = DocumentFolder.objects.get(parent_id=target)
        copied_child = DocumentFolder.objects.get(parent=copied_root)
        copied = Document.objects.get(folder=copied_child)
        self.assertEqual(copied.file.name, Document.objects.get(pk=doc).file.name)
        self.assertEqual(self.action('delete', folders=[root], reason='Remove subtree').status_code, 200)
        self.assertEqual(self.client.get(f'/api/documents/{doc}/download/').status_code, 404)
        self.assertEqual(self.action('restore', folders=[child]).status_code, 400)
        self.assertEqual(self.action('restore', folders=[root]).status_code, 200)
        self.assertIsNone(Document.objects.get(pk=doc).deleted_at)
        self.assertIsNotNone(Document.objects.get(pk=old).deleted_at)
        self.assertFalse(DocumentFolder.objects.filter(pk=child, deleted_at__isnull=False).exists())

    def test_deleted_folder_cannot_receive_upload(self):
        folder = self.folder()
        self.action('delete', folders=[folder], reason='Unused folder')
        response = self.client.post('/api/documents/', {'title':'Scheme', 'folder':folder,
            'file':SimpleUploadedFile('scheme.pdf', b'%PDF-1.4\ntest')}, format='multipart')
        self.assertEqual(response.status_code, 400)
