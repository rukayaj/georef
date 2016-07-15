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
from django.views.generic import View, UpdateView, CreateView
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
    '': 500,
    '1/4dg': 500,
    '5k': 5000,
    '2k': 2000,
    '100m': 100,
    '10m': 10,
    '50m': 50,
    'park': 500,
    '10k': 10000,
}


@login_required
def add_bulk(request):
    return render(request, 'website/add_bulk.html', {'input_columns': json.dumps(input_columns)})

@login_required
def import_csv(request):
    file_loc = 'C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\gazetteer\\SANBIGazetteer-extract.csv'
    df = pd.read_csv(file_loc, encoding="ISO-8859-1")

    # Check out what we think has been deduced from QDS
    def from_qds(x):
        diff = round(float(abs(x - round(x, 1))), 3)
        return diff == 0.035 or diff == 0.05

    # df['lat_from_qds'] = df['LAT'].apply(from_qds, axis=1)
    # df['long_from_qds'] = df['LONG'].apply(from_qds, axis=1)

    # Now we have to go through and see whether there are any localities with this particular locality string
    def create_georeference(row):
        print(row)
        # Create locality name
        try:
            locality_name = models.LocalityName.objects.get(locality_name=row['GAZNAME'])
        except models.LocalityName.DoesNotExist:
            print('already exists = ' + row['GAZNAME'])
            locality_name = models.LocalityName(locality_name=row['GAZNAME'])
            locality_name.save()

        # Create geolocation
        point = Point(row['LONG'], row['LAT'])
        #try:
        #    geographical_position = models.GeographicalPosition.objects.get(point__distance_lte=(point, 7000))
        #except models.GeographicalPosition.DoesNotExist:
        try:
            geographical_position = models.GeographicalPosition.objects.get(point=point)
        except models.GeographicalPosition.DoesNotExist:
            geographical_position = models.GeographicalPosition(point=point, notes=row['FEATYPE'],
                                                                origin=models.GeographicalPosition.GAZETTEER)
            #if row['Precision_m']:
            #    geographical_position.buffer = row['Precision_m']
            geographical_position.save()

        # Create georeference
        georeference = models.GeoReference(locality_name=locality_name,
                                           geographical_position=geographical_position)
        georeference.save()

    df.apply(create_georeference, axis=1)

    import pdb; pdb.set_trace()

@login_required
def import_shp(request, shp_name):
    from django.contrib.gis.gdal import DataSource
    root = 'C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\'
    # from django.contrib.gis.utils import LayerMapping
    #ds = DataSource('C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\rqis_rivers\\wriall500.shp')
    # https://www.arcgis.com/home/item.html?id=a600c0464b904dfcac0a4410ff56edc9
    file_loc = root + 'roads\\South Africa_Roads.shp'
    ds = DataSource(file_loc)
    layer = ds[0]
    print(layer.srs)

    for road in layer:
        ln = models.LocalityName(locality_name=str(road['ROADNO']))
        ln.save()
        print('saving locality name')
        gp = models.GeographicalPosition(line=road.geom.geos,
                                         feature_type=models.GeographicalPosition.ROAD,
                                         origin=models.GeographicalPosition.ROADS)
        gp.save()
        print('saving geo positoin')
        gr = models.GeoReference(locality_name=ln, geographical_position=gp)
        gr.save()
        print('saving geo ref')


@login_required
def index(request):
    georeferences = models.GeoReference.objects.filter(user=request.user, geographical_position=None)
    return render(request, 'website/outstanding_list.html', {'georeferences': georeferences})


@login_required
def completed(request):
    georeferences = models.GeoReference.objects.filter(user=request.user).exclude(geographical_position=None)
    return render(request, 'website/completed_list.html', {'georeferences': georeferences})


class DeleteGeoreference(SingleObjectMixin, View):
    model = models.GeoReference

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        return HttpResponse(status=204)


class GeoReferenceCreateView(CreateView):
    model = models.GeoReference
    template_name = 'website/single.html'

@login_required
def qc(request):
    # Automatically shown all done this month
    georeferences = models.GeoReference.objects.filter(created_on__year=datetime.date.today().year,
                                                       created_on__month=datetime.date.today().month)
    return render(request, 'website/qc_list.html', {'georeferences': georeferences})


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
    locality_name.clean_locality()

    return redirect('georeference', pk=pk)


def auto_geolocate(request, pk):
    georeference = models.GeoReference.objects.get(pk=pk)
    georeference.auto_geolocate()
    georeference.save()

    return redirect('georeference', pk=pk)


def set_geographical_position(request, pk):
    if request.POST:
        # Get the georeference that is being worked on
        georeference = models.GeoReference.objects.get(pk=pk)

        # Create the input geographical position from the post data
        geographical_position = forms.GeographicalPositionForm(request.POST)

        # Call is_valid first time and it gives an attribute error, the second time it returns true/false
        # Wtf. So I am just adding a try/except in here to call it once and ignore it
        try:
            print(geographical_position.is_valid())
        except AttributeError:
            print(geographical_position.is_valid())

        # After that bit of insanity we can get back to the normal world
        if geographical_position.is_valid():
            geographical_position = geographical_position.save()

            # Add it to our georeference and save
            georeference.geographical_position = geographical_position
            georeference.created_on = datetime.datetime.now()
            georeference.save()
        else:
            import pdb; pdb.set_trace()

    return redirect('index')


def process_bulk(request):
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
        if row['lat'] and row['long'] and row['res'] in llres_mapping:
            pos = models.GeographicalPosition(point=Point(row['long'], row['lat']),
                                              origin=models.GeographicalPosition.INPUT,
                                              precision=llres_mapping[row['res']])
            georeference.potential_geographical_positions = serialize('custom_geojson', [pos], geometry_field='point')

        georeference.auto_geolocate()
        print('saving georeference')
        # Save the georeference
        georeference.save()

    # Run a function to create the georeference tasks
    df.apply(create_georeference, axis=1)

    return redirect('index')
