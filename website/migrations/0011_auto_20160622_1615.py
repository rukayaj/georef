# -*- coding: utf-8 -*-
# Generated by Django 1.9.6 on 2016-06-22 14:15
from __future__ import unicode_literals

from django.conf import settings
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('website', '0010_auto_20160620_1711'),
    ]

    operations = [
        migrations.CreateModel(
            name='GeoReference',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('group_id', models.CharField(max_length=50)),
                ('unique_id', models.CharField(max_length=50)),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('notes', models.TextField()),
                ('potential_locations', django.contrib.postgres.fields.jsonb.JSONField()),
                ('geo_location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='website.GeoLocation')),
            ],
        ),
        migrations.RemoveField(
            model_name='localityname',
            name='geo_location',
        ),
        migrations.RemoveField(
            model_name='localityname',
            name='potential_geo_locations',
        ),
        migrations.RemoveField(
            model_name='localityname',
            name='source',
        ),
        migrations.AlterField(
            model_name='localityname',
            name='locality_name',
            field=models.TextField(help_text='The locality string'),
        ),
        migrations.AddField(
            model_name='georeference',
            name='locality_name',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='website.LocalityName'),
        ),
        migrations.AddField(
            model_name='georeference',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
    ]
