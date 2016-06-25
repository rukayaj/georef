from django.shortcuts import render
import json
from pandas.io.json import json_normalize
import pandas as pd
import datetime
from website import models
from django.contrib.gis.geos import Point, Polygon
from django.core.serializers import serialize
from django.http import HttpResponseRedirect, HttpResponse
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
import json
from django.core import serializers
from django.forms.models import model_to_dict
from django.views.generic import View, UpdateView
from django.views.generic.detail import SingleObjectMixin, DetailView
from website import forms


input_columns = ['unique_id',
                 'group',
                 'day',
                 'month',
                 'year',
                 'lat',
                 'long',
                 'res',
                 'locality']

llres_mapping = {
    '1/4dg': 500,
    '5k': 5000,
    '2k': 2000,
    '100m': 100,
    '10m': 10
}


@login_required
def add_bulk(request):
    return render(request, 'website/add_bulk.html', {'input_columns': json.dumps(input_columns)})


@login_required
def index(request):
    georeferences = models.GeoReference.objects.filter(user=request.user, geographical_position=None)
    return render(request, 'website/index.html', {'georeferences': georeferences})


@login_required
def completed(request):
    georeferences = models.GeoReference.objects.filter(user=request.user).exclude(geographical_position=None)
    return render(request, 'website/completed.html', {'georeferences': georeferences})


class DeleteGeoreference(SingleObjectMixin, View):
    model = models.GeoReference

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        return HttpResponse(status=204)


class GeoreferenceDetailView(DetailView):
    model = models.GeoReference
    template_name = "website/georeference.html"  # Defaults to georeference_detail.html
    context_object_name = 'georeference'

    def get_context_data(self, **kwargs):
        context = super(GeoreferenceDetailView, self).get_context_data(**kwargs)
        context['feature_type_choices'] = models.GeographicalPosition.feature_type_choices
        context['origin_choices'] = models.GeographicalPosition.origin_choices
        context['geographical_position_form'] = forms.GeographicalPositionForm()
        return context


class GeoReferenceUpdateView(UpdateView):
    model = models.GeoReference
    template_name = 'website/georeference.html'
    fields = ['notes']

    def get_context_data(self, **kwargs):
        context = super(GeoReferenceUpdateView, self).get_context_data(**kwargs)
        context['feature_type_choices'] = models.GeographicalPosition.feature_type_choices
        context['origin_choices'] = models.GeographicalPosition.origin_choices
        context['geographical_position_form'] = forms.GeographicalPositionForm()
        return context

def clean_locality(request, pk):
    """Just refreshes the locality - for debugging"""
    georeference = models.GeoReference.objects.get(pk=pk)
    locality_name = models.LocalityName.objects.get(pk=georeference.locality_name.pk)

    # We are going to try and split it apart, so init an empty dict for the json field
    locality_name.locality_parts = {'locality': locality_name.locality_name}

    # Removes the superfluous strings and standardises the language
    locality_name._clean_locality()
    locality_name._get_directions()
    locality_name._set_feature_type()
    locality_name._get_lat_long_dms()
    locality_name._get_lat_long_dd()

    locality_name.save()

    return redirect('georeference', pk=pk)


def auto_geolocate(request, pk):
    georeference = models.GeoReference.objects.get(pk=pk)
    georeference.auto_geolocate()
    georeference.save()

    return redirect('georeference')


def set_geographical_position(request, pk):
    if request.POST:
        # Get the georeference that is being worked on
        georeference = models.GeoReference.objects.get(pk=pk)

        # Create the input geographical position from the post data
        geographical_position = forms.GeographicalPositionForm(request.POST)

        # For reasons best known to itself Django likes to call is_valid just once on this thing before working
        # Seriously, call is_valid first time and it gives an attribute error, the second time it returns true/false
        # Wtf.
        try:
            print(geographical_position.is_valid())
        except AttributeError:
            print(geographical_position.is_valid())

        # After that bit of insanity we can get back to the normal world
        if geographical_position.is_valid():
            geographical_position = geographical_position.save()

            # Add it to our georeference and save
            georeference.geographical_position = geographical_position
            georeference.save()
        else:
            import pdb; pdb.set_trace()

    return redirect('index')


def process_locality(request):
    if request.is_ajax():
        # Get the locality name and date for georeferencing
        locality_name = request.POST['content[locality]']
        date = request.POST['content[date]']

        # Create a locality name object
        locality = models.LocalityName(locality_name=locality_name)

        # If given an extra point we need to plot it on the map
        if 'content[long]' in request.POST and 'content[lat]' in request.POST and 'content[res]' in request.POST:
            # Retrieve the input lat, long and res
            long = float(request.POST['content[long]'])
            lat = float(request.POST['content[lat]'])
            res = request.POST['content[res]']

            # Create a point using the above
            point = models.GeographicalPosition(point=Point(long, lat), origin=models.GeographicalPosition.INPUT, buffer=llres_mapping[res])

            # Add to model - not sure this is the right way to do it, do we actually need to store it in db?
            locality.potential_geographical_positions = [point]

        # Run auto geolocate to get an exhaustive list of all possible potential geo locations
        potential_geographical_positions = locality.auto_geolocate() # TODO add date=date here

        # Return the results
        return HttpResponse(json.dumps({'localities': potential_geographical_positions}))


def process(request):
    # Load the data into pandas
    data = json.loads(request.POST['data'])
    df = pd.DataFrame(data, columns=input_columns)

    # We need to do something about these if they are 0
    df.loc[df['day'] == 0, 'day'] = 1
    df.loc[df['month'] == 0, 'month'] = 1
    df['date'] = pd.to_datetime(pd.DataFrame({'year': df['year'],
                                              'month': df['month'],
                                              'day': df['day']})).dt.date
    del df['day'], df['month'],  df['year']

    # Send it back to the template - this is what we used to do
    # return render(request, 'website/process.html', {'data': df.to_json(orient='records')})

    # Get the input lat/long point data where we have it
    df['original_point'] = False

    # Create a Location object for all longdec & latdec inputs in the dataframe
    df.loc[pd.notnull(df['lat']) & pd.notnull(df['long']), 'original_point'] = \
        df.apply(lambda x:  models.GeographicalPosition(point=Point(x['long'], x['lat']),
                                               origin=models.GeographicalPosition.INPUT,
                                               buffer=llres_mapping[x['res']]), axis=1)

    # We don't need these fields any more, we've used them above
    del df['lat'], df['long'], df['res']

    # Now we have to go through and see whether there are any localities with this particular locality string
    def create_georeference(row):
        try:
            locality_name = models.LocalityName.objects.get(locality_name=row['locality'])
        except models.LocalityName.DoesNotExist:
            locality_name = models.LocalityName(locality_name=row['locality'])
            locality_name.save()

        # Now we need to create/check dates
        if 'date' in row and row['date']:
            try:
                date = models.LocalityDate.objects.get(locality_name=locality_name, date=row['date'])
            except models.LocalityDate.DoesNotExist:
                date = models.LocalityDate(locality_name=locality_name, date=row['date'])
                date.save()

        # Create the new georeference
        georeference = models.GeoReference(locality_name=locality_name,
                                           user=request.user,
                                           group_id=row['group'],
                                           unique_id=row['unique_id'])

        # Now we need to store original_point in our locality name
        if 'original_point' in row and row['original_point']:
            # georeference.potential_geographical_positions = serializers.serialize('json', [row['original_point'], ])
            # georeference.potential_geographical_positions = json.dumps([row['original_point']])
            # georeference.potential_geographical_positions = json.dumps(model_to_dict(row['original_point']))
            georeference.potential_geographical_positions = serialize('custom_geojson',
                                                             [row['original_point']],
                                                             geometry_field='point')

        georeference.auto_geolocate()
        print('saving georeference')
        # Save the georeference
        georeference.save()

    # Run a function to create the georeference tasks
    df.apply(create_georeference, axis=1)

    return redirect('index')
