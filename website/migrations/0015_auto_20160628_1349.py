# -*- coding: utf-8 -*-
# Generated by Django 1.9.6 on 2016-06-28 11:49
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0014_auto_20160627_1536'),
    ]

    operations = [
        migrations.AddField(
            model_name='geographicalposition',
            name='altitude',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='geographicalposition',
            name='notes',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='geographicalposition',
            name='origin',
            field=models.CharField(choices=[('US', 'User'), ('GO', 'Google'), ('GA', 'SANBI gazetteer'), ('GE', 'Geocode farm'), ('IN', 'Input'), ('RQ', 'South Africa 1:500 000 Rivers'), ('RO', 'Official list of roads'), ('UN', 'Unknown'), ('LS', 'Derived from locality string')], default='UN', max_length=2),
        ),
    ]
