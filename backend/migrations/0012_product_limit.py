# Generated by Django 4.2.1 on 2023-08-16 06:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('backend', '0011_rename_last_update_product_create_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='limit',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
