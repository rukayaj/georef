from django.shortcuts import render
import json
from pandas.io.json import json_normalize
import pandas as pd
import datetime
from website import models
from django.contrib.gis.geos import Point, Polygon, GEOSException
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
from django.db import connection


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
def add_single(request):
    if request.method == 'POST':
        form = forms.GeoReferenceSingleForm(request.POST)
        if form.is_valid():
            # Either retrieve an existing locality name, or add a new one
            try:
                locality_name = models.LocalityName.objects.get(locality_name=form.cleaned_data['locality_name'])
            except models.LocalityName.DoesNotExist:
                locality_name = models.LocalityName(locality_name=form.cleaned_data['locality_name'])
                locality_name.save()

            # Create and save georeference
            georeference = models.GeoReference(locality_name=locality_name, author=request.user.profile,)
            georeference.save()

            return redirect('index')
    else:
        form = forms.GeoReferenceSingleForm()

    return render(request, 'website/add_single.html', {'form': form})


@login_required
def add_bulk(request):
    return render(request, 'website/add_bulk.html', {'input_columns': json.dumps(input_columns)})


def import_sanbi(request):
    file_loc = 'C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\gazetteer\\Sanbi-Gazetteer.csv'
    import_csv(file_loc, models.Profile.objects.get(name='SANBI Gazetteer'))
    print("complete gazetteer")


def import_sabca(request):
    file_loc = 'C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\sabca\\SABCA_gazetteer.csv'
    import_csv(file_loc, models.Profile.objects.get(name='SABCA'))
    print("complete sabca")


def import_brahms(request):
    file_loc = 'C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\brahms\\brahms.csv'
    import_csv(file_loc, models.Profile.objects.get(name='BRAHMS'))
    print("complete brahms")
    file_loc = 'C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\sabca\\SABCA_gazetteer.csv'
    import_csv(file_loc, models.Profile.objects.get(name='SABCA'))
    print("complete sabca")
    file_loc = 'C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\gazetteer\\Sanbi-Gazetteer.csv'
    import_csv(file_loc, models.Profile.objects.get(name='SANBI Gazetteer'))
    print("complete gaz")


def import_csv(file_loc, importer):
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
        # If locality name is not a string then don't enter it
        try:
            row['locality'].lower()
        except AttributeError:
            return

        # Create locality name
        ln, created = models.LocalityName.objects.get_or_create(locality_name=row['locality'])

        # Create a point to use to retrieve or create a geographical position
        point = Point(row['long'], row['lat'])  # point__distance_lte=(point, 7000)
        gp, created = models.GeographicalPosition.objects.get_or_create(point=point)

        # Add feature if it exists, to be honest i'm not even sure we want to store this though...
        if 'feature' in row:
            ft, created = models.FeatureType.objects.get_or_create(type=row['feature'])
            gp.feature_type = ft
            gp.save()
            if created:
                print('Adding feature type... ' + row['feature'])

        # Add uncertainty if it exists
        if 'uncertainty' in row:
            if row['uncertainty'] in llres_mapping:
                gp.precision_m = llres_mapping[row['uncertainty']]
                gp.save()
            elif is_positive_number(row['uncertainty']):
                gp.precision_m = row['uncertainty']
                gp.save()

        # Create georeference
        georeference = models.GeoReference(locality_name=ln, geographical_position=gp, author=importer)

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
    root = 'C:\\Users\\JohaadienR\\Documents\\Projects\\python-sites\\georef-data-sources\\planetgis\\'

    # Keep track of all the layers we are adding in
    layers = ['District Municipalities 2016.kml',
              'Local Municipalities 2016.kml',
              'Wards 2016.kml',
              'Main Places.kml',
              'Sub Places.kml']

    for layer_name in layers:
        ds = DataSource(root + layer_name)
        for item in ds[0]:
            # Get name and location from layer
            locality_name = item.get('Name')
            try:
                polygon = Polygon(item.geom.coords[1][0])
            except GEOSException:
                continue

            # Get/create the geographical position, locality name and importer profile
            gp, created = models.GeographicalPosition.objects.get_or_create(polygon=polygon, precision_m=0)
            ln, created = models.LocalityName.objects.get_or_create(locality_name=locality_name)
            au, created = models.Profile.objects.get_or_create(name='Surveyor General')

            # Get/create the georeference using the above
            models.GeoReference.objects.get_or_create(locality_name=ln, geographical_position=gp, author=au)


@login_required
def index(request):
    georeferences = models.GeoReference.objects.filter(author__user=request.user, geographical_position=None)
    return render(request, 'website/outstanding_list.html', {'georeferences': georeferences})


@login_required
def completed(request):
    georeferences = models.GeoReference.objects.filter(author__user=request.user).exclude(geographical_position=None)
    return render(request, 'website/completed_list.html', {'georeferences': georeferences})


@login_required
def download_completed(request):
    # Create the HttpResponse object with the appropriate CSV header.
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="completed.csv"'

    writer = csv.writer(response)
    writer.writerow(['id', 'group', 'locality', 'lat', 'long', 'precision_m'])

    georeferences = models.GeoReference.objects.filter(author__user=request.user).exclude(geographical_position=None)
    for g in georeferences:
        if g.geographical_position.point:
            coords = g.geographical_position.point.coords
            precision_m = g.geographical_position.precision_m
        else:
            coords = g.geographical_position.polygon.centroid

            # Get the buffer length!
            cursor = connection.cursor()
            sql = 'select ST_Length(ST_LongestLine(gp.polygon, gp.polygon), true) from ' \
                  'website_geographicalposition as gp where gp.id = %s'

            cursor.execute(sql, [g.geographical_position.pk,])
            precision_m = cursor.fetchone()[0] / 2

        writer.writerow([g.unique_id, g.group_id, g.locality_name.locality_name, coords[0], coords[1], precision_m])

    return response


class DeleteGeoreference(SingleObjectMixin, View):
    model = models.GeoReference

    def post(self, request, *args, **kwargs):
        # Get the object
        self.object = self.get_object()

        # Before deleting it, get the locality_name and gp so we can delete if necessary
        locality_name = self.object.locality_name
        geographical_position = self.object.geographical_position
        self.object.delete()

        # Now the object has been deleted, is the locality name it created used anywhere else? if not then delete it
        georefs_ln = models.GeoReference.objects.filter(locality_name=locality_name).count()
        if georefs_ln == 0:
            locality_name.delete()

        # Do the same for the geographical position
        georefs_gp = models.GeoReference.objects.filter(geographical_position=geographical_position).count()
        if georefs_gp == 0:
            geographical_position.delete()

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

        if len(self.object.potential_georeferences.values()) < 2:
            self.object.auto_geolocate()
            self.object.save()

        context['feature_type_choices'] = models.FeatureType.objects.all()
        context['geographical_position_form'] = forms.GeographicalPositionForm()
        context['potential_geographical_positions'] = self.object.get_serialized_geolocations()

        same_collector = []
        if self.object.locality_date and self.object.group_id:
            date_upper = self.object.locality_date + relativedelta(months=+3)
            date_lower = self.object.locality_date + relativedelta(months=-3)
            same_collector_points = models.GeoReference.objects.filter(group_id=self.object.group_id,
                                                                       locality_date__range=[date_lower, date_upper],
                                                                       geographical_position__isnull=False)
            for p in same_collector_points:
                # p.geographical_position.origin = models.GeographicalPosition.SAME_GROUP
                p.geographical_position.notes = 'Visited by same collector on ' + formats.date_format(p.locality_date,
                                                                                                      "SHORT_DATE_FORMAT")
                # same_collector.append(p.geographical_position)
                same_collector.append(p)
        if same_collector:
            context['same_collector'] = serialize('custom_geojson', same_collector, geometry_field='point')

        if self.object.geographical_position:
            if self.object.geographical_position.point:
                context['geographical_position'] = serialize('geojson', [self.object.geographical_position, ],
                                                             geometry_field='point')
            else:
                context['geographical_position'] = serialize('geojson', [self.object.geographical_position, ],
                                                             geometry_field='polygon')

        return context


def clean_locality(request, pk):
    """Just refreshes the locality - for debugging"""
    georeference = models.GeoReference.objects.get(pk=pk)
    locality_name = models.LocalityName.objects.get(pk=georeference.locality_name.pk)

    # We are going to try and split it apart, so init an empty dict for the json field
    locality_name.clean_locality()
    locality_name.save()

    return redirect('georeference', pk=pk)


def auto_geolocate(request, pk):
    georeference = models.GeoReference.objects.get(pk=pk)
    georeference.auto_geolocate()
    georeference.save()

    return redirect('georeference', pk=pk)


def set_geographical_position(request, pk, gr_pk=False):
    if request.POST:
        # Get the georeference that is being worked on
        georeference = models.GeoReference.objects.get(pk=pk)

        # Create the input geographical position from the post data
        geographical_position = forms.GeographicalPositionForm(request.POST)

        # If the georeference/geographical position combo the user has chosen is pre-existing in db then just copy it
        if gr_pk:
            chosen_georeference = models.GeoReference.objects.get(pk=gr_pk)
            georeference.geographical_position = chosen_georeference.geographical_position

            # We need to update the precision for this geographical position
            geographical_position.is_valid()
            georeference.geographical_position.precision_m = geographical_position.cleaned_data['precision_m']
            georeference.geographical_position.save()

            # Update created date for georeference
            georeference.created_on = datetime.datetime.now()
            georeference.save()
        else:
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
                import pdb
                pdb.set_trace()

    return redirect('index')


def process_bulk(request):
    # Load the data into pandas
    data = json.loads(request.POST['data'])
    for row in data:
        if row[input_columns.index('locality')] is None:
            continue
        if row[input_columns.index('locality')].strip() == '':
            continue
        try:
            locality_name = models.LocalityName.objects.get(locality_name=row[input_columns.index('locality')])
        except models.LocalityName.DoesNotExist:
            locality_name = models.LocalityName(locality_name=row[input_columns.index('locality')])
            locality_name.save()

        # Create the new georeference
        georeference = models.GeoReference(locality_name=locality_name,
                                           author=request.user.profile,
                                           group_id=row[input_columns.index('group')],
                                           unique_id=row[input_columns.index('unique_id')])

        # Now we need to create/check dates
        try:
            if row[input_columns.index('day')] == 0:
                row[input_columns.index('day')] = 1
            if row[input_columns.index('month')] == 0:
                row[input_columns.index('month')] = 1
            georeference.locality_date = datetime.date(day=row[input_columns.index('day')],
                                                       month=row[input_columns.index('month')],
                                                       year=row[input_columns.index('year')])
        except:
            pass

        # Now we need to store original_point in our locality name
        if row[input_columns.index('lat')] and row[input_columns.index('long')]:
            try:
                if row[input_columns.index('lat')] > 0:
                    row[input_columns.index('lat')] *= -1
                long = row[input_columns.index('long')]
                lat = row[input_columns.index('lat')]
                precision_m = False
                if row[input_columns.index('res')]:
                    if row[input_columns.index('res')] in llres_mapping:
                        precision_m = llres_mapping[row[input_columns.index('res')]]
                if precision_m:
                    georeference.add_potential_georeference(lat=lat, long=long,
                                                            profile_name=request.user.profile.name,
                                                            precision_m=precision_m)
                else:
                    georeference.add_potential_georeference(lat=lat, long=long,
                                                            profile_name=request.user.profile.name)
            except ValueError:
                print('problem with lat/long')

        # Everything's cool, let's save
        georeference.save()

    return redirect('index')
