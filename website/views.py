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
from django.utils import formats
from dateutil.relativedelta import relativedelta
import csv
from django.http import HttpResponse


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
    '0.25k': 250,
    '1/2dg': 55000,
    '1/4dg': 27500,
    '1000m': 1000,
    '100k': 100000,
    '100m': 100,
    '10k': 10000,
    '10m': 10,
    '1dg': 110000,
    '1k+': 1000,
    '250m': 250,
    '2k': 2000,
    '500m': 500,
    '50k': 50000,
    '50m': 50,
    '5k': 5000,
    'farm': None,
    'park': None
}


@login_required
def add_bulk(request):
    return render(request, 'website/add_bulk.html', {'input_columns': json.dumps(input_columns)})


def import_sanbi(request):
    file_loc = 'C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\gazetteer\\SANBIGazetteer-extract.csv'
    import_csv(file_loc, models.GeographicalPosition.GAZETTEER)
    print("complete")


def import_sabca(request):
    file_loc = 'C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\sabca\\SABCA_gazetteer.csv'
    import_csv(file_loc, models.GeographicalPosition.SABCA)
    print("complete sabca")


def import_brahms(request):
    file_loc = 'C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\brahms\\brahms.csv'
    import_csv(file_loc, models.GeographicalPosition.BRAHMS)
    print("complete brahms")
    file_loc = 'C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\sabca\\SABCA_gazetteer.csv'
    import_csv(file_loc, models.GeographicalPosition.SABCA)
    print("complete sabca")
    file_loc = 'C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\gazetteer\\SANBIGazetteer-extract.csv'
    import_csv(file_loc, models.GeographicalPosition.GAZETTEER)
    print("complete")


def import_csv(file_loc, origin):
    df = pd.read_csv(file_loc, encoding="utf-8")  # ISO-8859-1

    # Check out what we think has been deduced from QDS
    def from_qds(x):
        diff = round(float(abs(x - round(x, 1))), 3)
        return diff == 0.035 or diff == 0.05

    # Useful for determining if we have a useable number for the buffer
    def is_positive_number(s):
        try:
            number = int(s)
            if number < 0:
                return False
            return True
        except ValueError:
            return False

    # Function used to create a georeference for each row
    def create_georeference(row):
        # Monitoring...
        # print(row['locality'])
        # If locality name is not a string then don't enter it
        try:
            row['locality'].lower()
        except AttributeError:
            return

        # Create locality name
        try:
            locality_name = models.LocalityName.objects.get(locality_name=row['locality'])
        except models.LocalityName.DoesNotExist:
            locality_name = models.LocalityName(locality_name=row['locality'])
            locality_name.save()

        # Create geolocation
        point = Point(row['long'], row['lat'])
        try:
            geographical_position = models.GeographicalPosition.objects.get(
                point=point)  # point__distance_lte=(point, 7000)
        except models.GeographicalPosition.DoesNotExist:
            geographical_position = models.GeographicalPosition(point=point, origin=origin)
            if 'feature' in row:
                geographical_position.notes = row['feature']
            if 'uncertainty' in row:
                if row['uncertainty'] in llres_mapping:
                    geographical_position.buffer = llres_mapping[row['uncertainty']]
                elif is_positive_number(row['uncertainty']):
                    geographical_position.buffer = row['uncertainty']
            geographical_position.save()

        # Create georeference
        georeference = models.GeoReference(locality_name=locality_name,
                                           geographical_position=geographical_position)

        # If there's a collector number then add it
        if 'group' in row:
            georeference.group_id = row['group'].strip()

        # If possible add a date
        if 'day' in row and 'month' in row and 'year' in row:
            try:
                row['month'] = int(round(row['month']))
                row['day'] = int(round(row['day']))
                row['year'] = int(round(row['year']))
                if row['year'] > 0:
                    if row['day'] < 1:
                        row['day'] = 1
                    if row['month'] < 1:
                        row['month'] = 1
                    georeference.locality_date = datetime.datetime(year=row['year'], month=row['month'], day=row['day'])
            except Exception:
                pass

        # Save georeference
        georeference.save()

    df.apply(create_georeference, axis=1)


@login_required
def import_shp(request, shp_name):
    from django.contrib.gis.gdal import DataSource
    root = 'C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\'
    # from django.contrib.gis.utils import LayerMapping
    # ds = DataSource('C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\rqis_rivers\\wriall500.shp')
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


@login_required
def download_completed(request):
    # Create the HttpResponse object with the appropriate CSV header.
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="completed.csv"'

    writer = csv.writer(response)
    writer.writerow(['id', 'group', 'locality', 'lat', 'long'])

    georeferences = models.GeoReference.objects.filter(user=request.user).exclude(geographical_position=None)
    for g in georeferences:
        coords = g.geographical_position.point.coords
        writer.writerow([g.unique_id, g.group_id, g.locality_name.locality_name, coords[0], coords[1]])

    return response

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
                                                       created_on__month=datetime.date.today().month)[:1000]
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

        same_collector = get_same_collector_points(self.object)
        if same_collector:
            context['same_collector'] = serialize('custom_geojson', same_collector, geometry_field='point')

        return context

def get_same_collector_points(geo_reference):
    # Ok now get all of the points which have been successfully geolocated with the same collector number in the same year
    same_collector = []
    if geo_reference.locality_date and geo_reference.group_id:
        date_upper = geo_reference.locality_date + relativedelta(months=+3)
        date_lower = geo_reference.locality_date + relativedelta(months=-3)
        same_collector_points = models.GeoReference.objects.filter(group_id=geo_reference.group_id,
                                                                   locality_date__range=[date_lower, date_upper],
                                                                   geographical_position__isnull=False)
        for p in same_collector_points:
            p.geographical_position.origin = models.GeographicalPosition.SAME_GROUP
            p.geographical_position.notes = 'Visited by same collector on ' + formats.date_format(p.locality_date,
                                                                                                  "SHORT_DATE_FORMAT")
            same_collector.append(p.geographical_position)
    return same_collector




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
            import pdb;
            pdb.set_trace()

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
    del df['day'], df['month'], df['year']

    # Send it back to the template - this is what we used to do
    # return render(request, 'website/process.html', {'data': df.to_json(orient='records')})

    # Now we have to go through and see whether there are any localities with this particular locality string
    def create_georeference(row):
        try:
            locality_name = models.LocalityName.objects.get(locality_name=row['locality'])
        except models.LocalityName.DoesNotExist:
            locality_name = models.LocalityName(locality_name=row['locality'])
            locality_name.save()

        # Create the new georeference
        georeference = models.GeoReference(locality_name=locality_name,
                                           user=request.user,
                                           group_id=row['group'],
                                           unique_id=row['unique_id'])

        # Now we need to create/check dates
        if 'date' in row and row['date']:
            georeference.locality_date = row['date']

        # Now we need to store original_point in our locality name
        if 'lat' in row and 'long' in row:
            if row['lat'] and row['long']:
                if row['lat'] > 0:
                    row['lat'] = row['lat'] * -1
                pos = models.GeographicalPosition(point=Point(row['long'], row['lat']),
                                                  origin=models.GeographicalPosition.INPUT)
                if 'res' in row:
                    if row['res'] in llres_mapping:
                        pos.precision = llres_mapping[row['res']]
                georeference.potential_geographical_positions = serialize('custom_geojson', [pos], geometry_field='point')

        georeference.auto_geolocate()
        print('saving georeference')
        # Save the georeference
        georeference.save()

    # Run a function to create the georeference tasks
    df.apply(create_georeference, axis=1)

    return redirect('index')
