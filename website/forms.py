from django import forms
from website import models
from django.forms import ModelForm


class GeographicalPositionForm(ModelForm):
    class Meta:
        model = models.GeographicalPosition
        fields = ['point', 'polygon', 'precision_m']
        widgets = {
            'point': forms.HiddenInput(),
            'polygon': forms.HiddenInput(),
        }


class GeoReferenceNotesForm(ModelForm):
    class Meta:
        model = models.GeoReference
        fields = ['notes']


class GeoReferenceSingleForm(forms.Form):
    locality_name = forms.CharField(label="Locality name", max_length=250)

