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
    '100m': 100
}


def index(request):
    return render(request, 'website/index.html', {'input_columns': json.dumps(input_columns)})


def set_georeference(request):
    if request.is_ajax():
        if 'content[id]' in request.POST:
            # It is a geolocation from our own database
            return HttpResponse(json.dumps({'success': True}))

        # Get the variables from the post request
        locality_name = request.POST['content[locality]']
        date = request.POST['content[date]']
        coordinates = request.POST['content[coordinates]']
        source = request.POST['content[source]']
        res = request.POST['content[resolution]']

        # Create a Geo Location object

        # Create a Locality Name object
        locality = models.LocalityName(locality_name=locality_name)

        return HttpResponse(json.dumps({'success': True}))


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
            point = models.GeoLocation(point=Point(long, lat), origin=models.GeoLocation.INPUT, buffer=llres_mapping[res])

            # Add to model - not sure this is the right way to do it, do we actually need to store it in db?
            locality.potential_geo_locations = [point]

        # Run auto geolocate to get an exhaustive list of all possible potential geo locations
        potential_geo_locations = locality.auto_geolocate() # TODO add date=date here

        # Return the results
        return HttpResponse(json.dumps({'localities': potential_geo_locations}))


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

    # Get the input lat/long point data where we have it
    # df['original_point'] = False

    # Create a Location object for all longdec & latdec inputs in the dataframe
    #df.loc[pd.notnull(df['lat']) & pd.notnull(df['long']), 'original_point'] = \
    #    df.apply(lambda x:  models.GeoLocation(point=Point(x['long'], x['lat']),
    #                                           origin=models.GeoLocation.INPUT,
    #                                           buffer=llres_mapping[x['res']]), axis=1)

    # Serialize that Location object into geojson so that it's easily accessible in the template
    # df.loc[pd.notnull(df['lat']) & pd.notnull(df['long']), 'original_point'] = \
    #    df.apply(lambda x:  serialize('custom_geojson',
    #                                  [x['original_point']],
    #                                  geometry_field='point'), axis=1)

    # We don't need these fields any more, we've used them above
    #del df['lat'], df['long'], df['res']

    # Create a Locality Name object from the locality ready for georeferencing
    #df['locality_name'] = df.apply(lambda x: models.LocalityName(locality_name=x['locality'],
    #                                                             date=x['date'],
    #                                                             potential_geo_locations=x['original_point']), axis=1)
    #del df['locality'], df['date'], df['original_point']

    # Try and automatically georeference it (gathers different options)
    #df['locality_name'].apply(lambda x: x.auto_geolocate())
    #import pdb; pdb.set_trace()

    # Group by date collected & collector?

    # Send it back to the template
    return render(request, 'website/process.html', {'data': df.to_json(orient='records')})
    #   # .to_html(classes="table table-striped") .to_json()df.to_dict(orient='records')

    

    # - Locality parts:

    # Lat/long

    # - Eg. Nieuwoudtville. Oorlogskloof Nature Reserve. Western Cape.
    # Place 1
    # Place 2
    # Place 3, etc

    # - Eg. Namaqualand, naby Spitskop. Lake Panic near Skukuza; Kruger National Park
    # Near
    # Place

    # - EG 20km N of Cape Town
    # Distance
    # Direction
    # Place

    # Farm name
    # Farm number

    # Reserve/Game farm/park

    # Road

