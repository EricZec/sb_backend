# Generated by Django 4.2.1 on 2023-08-06 12:10

from django.db import migrations
import django_fsm


class Migration(migrations.Migration):

    dependencies = [
        ('backend', '0008_alter_order_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='status',
            field=django_fsm.FSMField(choices=[('a', 'Awaiting payment'), ('b', 'Processed'), ('c', 'Shipped'), ('d', 'Completed'), ('p', 'Cancelled')], default='a', max_length=1),
        ),
    ]