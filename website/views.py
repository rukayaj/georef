from django.shortcuts import render
import json
from pandas.io.json import json_normalize
import pandas as pd
import datetime
from website import models
from django.contrib.gis.geos import Point

input_columns = ['brahms', 'collector_number', 'collected_day', 'collected_month', 'collected_year', 'latdec', 'longdec', 'llres', 'locality']


def index(request):
    return render(request, 'website/index.html', {})


def process(request):
    # Load the data into pandas
    data = json.loads(request.POST['data'])
    df = pd.DataFrame(data, columns=input_columns)

    # We need to do something about these if they are 0
    df.loc[df['collected_day'] == 0, 'collected_day'] = 1
    df.loc[df['collected_month'] == 0, 'collected_month'] = 1
    df['collected'] = pd.to_datetime(pd.DataFrame({'year': df['collected_year'],
                                                   'month': df['collected_month'],
                                                   'day': df['collected_day']})).dt.date
    del df['collected_day'], df['collected_month'],  df['collected_year']

    # Get the input point data where we have it
    df['original_point'] = False
    df.loc[pd.notnull(df['latdec']) & pd.notnull(df['longdec']), 'original_point'] = df.apply(lambda x: Point(x['longdec'], x['latdec']).json, axis=1)
    del df['latdec'], df['longdec']

    # Create a Georeference object from the locality, this automatically runs it through all possible options to georeference it
    df['georeference'] = df['locality'].apply(lambda x: models.Georeference(locality=x))

    # Group by date collected & collector?

    # Send it back to the template
    return render(request, 'website/process.html', {'data': df.to_dict(orient='records')})  # .to_html(classes="table table-striped") .to_json()

    

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

