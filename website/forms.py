from django import forms
from website import models
from django.forms import ModelForm


class GeographicalPositionForm(ModelForm):
    class Meta:
        model = models.GeographicalPosition
        fields = ['point', 'feature_type', 'precision']
        widgets = {
            'point': forms.HiddenInput(),
        }


class GeoReferenceNotesForm(ModelForm):
    class Meta:
        model = models.GeoReference
        fields = ['notes']

