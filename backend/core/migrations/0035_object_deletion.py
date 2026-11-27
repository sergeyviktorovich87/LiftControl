from django.db import migrations,models


class Migration(migrations.Migration):
    dependencies=[('core','0034_building_tickets')]
    operations=[
        migrations.AddField(model_name='building',name='deleted_at',field=models.DateTimeField(blank=True,db_default=None,db_index=True,null=True)),
        migrations.AddField(model_name='elevator',name='deleted_at',field=models.DateTimeField(blank=True,db_default=None,db_index=True,null=True)),
        migrations.RemoveConstraint(model_name='elevator',name='organization_factory_number'),
        migrations.RemoveConstraint(model_name='elevator',name='organization_inventory_number'),
        migrations.AddConstraint(model_name='elevator',constraint=models.UniqueConstraint(fields=['organization','factory_number'],condition=models.Q(deleted_at__isnull=True),name='organization_factory_number')),
        migrations.AddConstraint(model_name='elevator',constraint=models.UniqueConstraint(fields=['organization','inventory_number'],condition=~models.Q(inventory_number='') & models.Q(deleted_at__isnull=True),name='organization_inventory_number')),
    ]
