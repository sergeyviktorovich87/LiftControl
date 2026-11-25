import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0030_document_folders')]
    operations = [
        migrations.CreateModel(
            name='LiftDocumentFolder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('updated_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='core.organization')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='core.liftdocumentfolder')),
                ('elevators', models.ManyToManyField(blank=True, related_name='document_folders', to='core.elevator')),
            ], options={'ordering': ['name', 'pk']},
        ),
        migrations.AddField(model_name='liftdocument', name='folder', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='core.liftdocumentfolder')),
        migrations.AddField(model_name='liftdocument', name='updated_at', field=models.DateTimeField(default=django.utils.timezone.now)),
        migrations.AlterField(model_name='liftdocument', name='elevator', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='lift_documents', to='core.elevator')),
    ]
