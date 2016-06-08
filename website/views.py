from django.shortcuts import render
import json
from pandas.io.json import json_normalize
import pandas as pd
import datetime
from website import models
from django.contrib.gis.geos import Point, Polygon
from django.core.serializers import serialize

input_columns = ['brahms', 'collector_number', 'collected_day', 'collected_month', 'collected_year', 'latdec', 'longdec', 'llres', 'locality']


def index(request):
    return render(request, 'website/index.html', {})


def set_georeference(request):
    # if not location: (it's user created just now on the map)
    #   create location
    # else:
    #   retrieve location

    # Create a new georeference object
    pass


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
    df['original_point'] = False
    llres_mapping = {
        '1/4dg': 500,
        '5k': 5000,
        '2k': 2000,
        '100m': 100
    }

    # Create a Location object for all longdec & latdec inputs in the dataframe
    df.loc[pd.notnull(df['latdec']) & pd.notnull(df['longdec']), 'original_point'] = \
        df.apply(lambda x:  models.GeoLocation(point=Point(x['longdec'], x['latdec']),
                                               origin=models.GeoLocation.INPUT,
                                               buffer=llres_mapping[x['llres']]))

    # Serialize that Location object into geojson so that it's easily accessible in the template
    df.loc[pd.notnull(df['latdec']) & pd.notnull(df['longdec']), 'original_point'] = \
        df.apply(lambda x:  serialize('custom_geojson',
                                      [x['original_point']],
                                      geometry_field='point'), axis=1)

    # We don't need these fields any more, we've used them above
    del df['latdec'], df['longdec']

    # Create a Locality Name object from the locality ready for georeferencing
    df['locality_name'] = df.apply(lambda x: models.LocalityName(locality=x['locality'],
                                                                 date=x['date'],
                                                                 potential_geo_locations=x['original_point']))
    del df['locality'], df['date'], df['original_point']

    # Try and automatically georeference it (gathers different options)
    # df['georeference'].apply(lambda x: x.auto_geolocate())

    # Group by date collected & collector?

    # Send it back to the template
    return render(request, 'website/process.html', {'data': df.to_json()})
    # df.to_dict(orient='records')})  # .to_html(classes="table table-striped") .to_json()

    

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

