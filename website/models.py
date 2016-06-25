from django.contrib.gis.db import models
from django.contrib.postgres.fields import JSONField
from django.core.urlresolvers import reverse
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User, Group
from django.utils import formats
import re
import sys
from enum import Enum
from django.contrib.postgres.fields import IntegerRangeField, ArrayField
from django.contrib.gis.geos import Point, GeometryCollection
# Google maps geolocating API - https://github.com/geopy/geopy
from geopy.geocoders import GoogleV3
from django.db.models.signals import post_init
from django.dispatch import receiver
from django.core.serializers import serialize
from django.contrib.auth.models import User
from djgeojson.serializers import Deserializer as GeoJSONDeserializer


class GeographicalPosition(models.Model):
    # Geographical location that has either a point or a polygon
    point = models.PointField(null=True, blank=True)
    polygon = models.PolygonField(null=True, blank=True)

    # The type of location
    TOWN = 'T'
    MOUNTAIN = 'M'
    RAILWAY = 'R'
    FARM = 'F'
    PARK = 'P'
    UNKNOWN = 'U'
    feature_type_choices = (
        (TOWN, 'town'),
        (MOUNTAIN, 'mountain'),
        (RAILWAY, 'railway'),
        (FARM, 'farm'),
        (PARK, 'park'),
        (UNKNOWN, 'unknown')
    )
    feature_type = models.CharField(max_length=1, choices=feature_type_choices, default=UNKNOWN)

    # Determines the resolution this point has been georeferenced to
    # No I think it is right. Georeference 1 "Slangkop" or 2 "Snakehead" should both lead to the same point and the
    # buffer should be associated with that point, if you can georef it finer then do it and change buffer + lat/long
    buffer = models.IntegerField(null=True, blank=True)

    # Origin of the point/polygon
    USER = 'US'
    GOOGLE = 'GO'
    INPUT = 'IN'
    UNKNOWN = 'UN'
    origin_choices = (
        (USER, 'User'),
        (GOOGLE, 'Google'),
        (INPUT, 'Input'),
        (UNKNOWN, 'Unknown')
    )
    origin = models.CharField(max_length=2, choices=origin_choices, default=UNKNOWN)

    def clean(self):
        # If it's not got a point or polygon or it's got a point and a polygon raise error
        if (not self.location_point and not self.polygon) or (self.location_point and self.polygon):
            raise ValidationError('Either store point or polygon.')


class LocalityName(models.Model):
    # Keep a record of when this was added to the database
    created_on = models.DateTimeField(auto_now_add=True)

    # The main part of this model is the locality name e.g. "Cape Town"
    locality_name = models.TextField(help_text='The locality string')

    # Parts of the locality name, cleaned
    locality_parts = JSONField()

    def __str__(self):
        return self.locality_name

    def _get_lat_long_dms(self):
        # See if it contains some degrees/minutes/seconds in the string itself
        regex = '\s[sS][\s\.](\d\d)[\s\.d](\d\d)[\s\.m](\d\d)(\.\d+)?s?\s*,?\s*[eE][\s\.](\d\d)[\s\.d](\d\d)[\s\.m](\d\d)(\.\d+)?s?\s'
        match = re.search(regex, str(self.locality_parts['locality']))
        if match:
            south = {'degrees': float(match.group(1)), 'minutes': float(match.group(2)),
                     'seconds': float(match.group(3))}
            east = {'degrees': float(match.group(5)), 'minutes': float(match.group(6)),
                    'seconds': float(match.group(7))}
            lat = south['degrees'] + south['minutes'] / 60 + south['seconds'] / 3600
            long = east['degrees'] + east['minutes'] / 60 + east['seconds'] / 3600

            # Remove from the locality string
            self.locality_parts['locality'] = re.sub(regex, '', str(self.locality_parts['locality']))
            self.locality_parts['lat'] = lat
            self.locality_parts['long'] = long

    def _get_lat_long_dd(self):
        # See if it contains decimal degrees in the string itself
        regex = r'(-?[1-4][1-4]\.[0-9]+),\s+(-?[1-4][1-4]\.[0-9]+)'
        match = re.search(regex, str(self.locality_parts['locality']))
        if match:
            lat = float(match.group(1))
            long = float(match.group(2))
            self.locality_parts['locality'] = re.sub(regex, '', str(self.locality_parts['locality']))

            # Just be aware that we assume here that there is no lat/long in here
            self.locality_parts['lat'] = lat
            self.locality_parts['long'] = long

    def _clean_locality(self):
        # A simple dictionary to try and standardise the language a bit, don't run as case sensitive
        standardise_language = [
            {'replace': 'Farm',
             'regex': [r'\s+plaas\s+', r'[\w\s]+?\s*[oi]n\s+(the\s+)?farm\s*']},
            {'replace': 'Forest',
             'regex': [r'\s+for\.']},
            {'replace': 'Nature Reserve',
             'regex': [r'\s+nat\.?\s+res\.?', r'\s+n\.?\s?r\.?', r'nr\.']},
            {'replace': 'Game Reserve',
             'regex': [r'\s+game\s+res\.']},
            {'replace': 'Reserve',
             'regex': [r'\s+res\.']},
            {'replace': 'National Park',
             'regex': [r'\s+nat\.?\s+park\.?', r'\s+n(at)?\.?\s?p(ark)?\.?\s+']},
            {'replace': 'District',
             'regex': [r'\s+dist(\.|\s+)', r'\s+div(\.|\s+)']},
            {'replace': 'Station',
             'regex': [r'\s+sta(\.|\s+)']},
            {'replace': 'Mountain',
             'regex': [r'\s+mn?t(\.|\s+)']},
            {'replace': 'near',
             'regex': [r'\s+nr\.?\s+', r'\s+naby\s+', r'nearby', r'above', r'below', r'behind',
                       r'\s+in\s*front\s+(of\s+)?', r'\s+ne(ar|xt|arby)\s+to', r'\s+skirting']},
            {'replace': 'between',
             'regex': [r'\s+betw?n?\.?(\.|\s+)']},
            {'replace': '',
             'regex': [r'^collected\s+(from|in|on)?\s*', r'\s+along', r'\s+the']},
        ]

        # Run a place through it
        for item in standardise_language:
            for reg in item['regex']:
                self.locality_parts['locality'] = re.sub(reg, ' ' + item['replace'], self.locality_parts['locality'],
                                                         flags=re.IGNORECASE)

        # Set major area and remove it from string
        provinces = [
            {'replace': 'Northern Cape',
             'regex': [r'\s+nc(\.|\s+)', 'SAF-NC']},
            {'replace': 'Free State',
             'regex': [r'\s+F(\.|\s+)', r'\s+FS(\.|\s+)', 'SAF-FS']},
            {'replace': 'Gauteng',
             'regex': ['Gauteng & Mphum', 'Gautng or Lstho', 'SAF-GA', r'\s+GP(\.|\s+)', 'SAF-TV']},
            {'replace': 'KwaZulu Natal',
             'regex': [r'\s+K-N', r'\s+KZ(\.|\s+)', r'\s+KZN(\.|\s+)', 'SAF-KN']},
            {'replace': 'Limpopo',
             'regex': [r'\s+Lim(\.|\s+)', r'\s+Lm(\.|\s+)', r'\s+LP(\.|\s+)', r'\s+NP(\.|\s+)',
                       'Northern Provin', 'Northern Province', 'SAF-LP', 'SAF-TV']},
            {'replace': 'Mpumalanga',
             'regex': [r'\s+MP(\.|\s+)', 'SAF-MP', 'SAF-TV']},
            {'replace': 'North West',
             'regex': [r'\s+NW$', 'SAF-NW', 'SAF-TV']},
            {'replace': 'Western Cape',
             'regex': [r'\s+WC(\.|\s+)', r'\s+WP(\.|\s+)', 'SAF-CP', 'SAF-WC']},
            {'replace': 'Eastern Cape',
             'regex': ['SAF-EC', r'\s+EC(\.|\s+)']}
        ]
        for item in provinces:
            for reg in item['regex']:
                temp = re.sub(reg, '', self.locality_parts['locality'], flags=re.IGNORECASE)
                if temp != self.locality_parts['locality']:
                    self.locality_parts['locality'] = temp
                    self.locality_parts['province'] = item['replace']

        # Do we want to split up places in the string if possible?
        phrases = [
            'at foot of',
            'along the top of',
            'at the bottom of',
            'nearby'
        ]

    def _get_directions(self):
        # If there's something in front of it and something behind it, i.e., ^muizenberg, 20 km s of tokai$
        # we really don't want to use the directions then, rather use the main thing and strip out the rest
        main_regex = '\s*(\d\d*[,\.]?\d*)\s*(k?m|miles)\s+(([swne]{1,3})|south|no?rth|east|west)\s*(of|fro?m)?\s*'
        m = re.search(r'^(.+?)' + re.escape(main_regex) + '(.+)$', self.locality_parts['locality'], re.IGNORECASE)
        if m:
            self.locality_parts['locality'] = m.group(1)
            return

        # We store the locality variable and try and substitute stuff in it
        locality = self.locality_parts['locality']

        # Look for digits and measurement units
        measurement_units = {'miles': ['miles', 'mile', 'mi'],
                             'yards': ['yard', 'yards'],
                             'kilometers': ['km', 'kmeters', 'kmetres', 'kilometers', 'kmeter', 'kms', 'kmetre',
                                            'kilometer'],
                             'meters': ['m', 'meters', 'metres', 'meter', 'metre', 'ms'],
                             'feet': ['ft', 'feet']}

        # For loops in python do not have scope so the distance var declared within it is available outside
        # But for clarity I am declaring distance here too
        km_distance = False

        # Loop through miles, yards,
        for measurement_unit, variations in measurement_units.items():
            for variation in variations:
                # Looking for 23.5 kmeters, 1,2 mi, 234,6 kms, etc
                regex = '\s*(\d\d*[,\.]?\d*)\s*(' + variation + ')'

                # Find matches
                match = re.search(regex, locality, re.IGNORECASE)
                if match:
                    # Convert the distance string to a float, replace the , with . for decimal points
                    km_distance = float(match.group(1).replace(',', '.'))

                    # Do some conversion for the different measurement units - we standardise to km
                    if measurement_unit == 'miles':
                        km_distance *= 1.60934
                    elif measurement_unit == 'meters':
                        km_distance *= 0.001
                    elif measurement_unit is 'feet':
                        km_distance *= 0.0003048
                    elif measurement_unit is 'yards':
                        km_distance *= 0.0009144

                    # Remove it from the locality string
                    locality = re.sub(regex, '', locality, re.IGNORECASE)

                    # Break out of both loops, we've found the distance/measurements
                    break

        # Look for bearings, keep track of the ones we need to remove and get rid of them afterwards
        bearings_matches = {'south': ['south', 's', 'se', 'sw', 'south-east', 'southeast', 'south-west', 'southwest'],
                            'north': ['north', 'n', 'ne', 'nw', 'north-east', 'northeast', 'north-west', 'northwest'],
                            'east': ['east', 'e', 'se', 'ne', 'south-east', 'southeast', 'north-east', 'northeast'],
                            'west': ['west', 'w', 'sw', 'nw', 'south-west', 'southwest', 'north-west', 'northwest']}
        bearings = []
        strings_to_remove = set()  # apparently keeps unique values only
        for proper_name, match_list in bearings_matches.items():
            for match in match_list:
                regex = '\s(' + match + ')\.?(\s|$)'
                temp = re.sub(regex, '', locality, flags=re.IGNORECASE)
                if temp is not locality:
                    bearings.append(proper_name)
                    strings_to_remove.add(regex)

        # Remove all of the applicable bearings
        for regex in strings_to_remove:
            locality = re.sub(regex, '', locality, flags=re.IGNORECASE)

        # If we have bearings and distance and measurement we can make a sensible set of directions to return
        if bearings and km_distance:
            # Clean up the locality string some more - e.g. if string is 96 km north [of/from] cape town
            locality = re.sub('([oO]f|[fF]ro?m)', '', locality)

            # This seems to be if we're left with , or ;, but not sure why removing?
            locality = re.sub('^\s*[\.,;]', '', locality)
            locality = re.sub('\s*[\.,;]$', '', locality)

            # Save the different cleaned locality parts
            self.locality_parts['locality'] = locality.strip()
            self.locality_parts['bearings'] = bearings
            self.locality_parts['km_distance'] = km_distance
        else:
            return

    def _set_feature_type(self):
        temp = self.locality_parts['locality']

        # Remove "in the / on the" for farms
        self.locality_parts['locality'] = re.sub(r'[\w\s]+?\s*[OoIi]n\s+(the\s+)?[Ff]arm\s*', 'Farm',
                                                 self.locality_parts['locality'])

        # Farm x, blah blah blah (we don't need the blah blah blah bit, so remove it and strip out the "Farm"
        self.locality_parts['locality'] = re.sub(r'^\s*Farm\s*(.+?),.+', "\g<1>", self.locality_parts['locality'])

        # If this string contains three digits it's very likely to be a farm number
        # Alternate regex ^(([A-Za-z\-]+\s*?){1,4}),?\s?[\(\[\{]?(\d{3})[^\.].*$
        results = re.search('\s*[\[\{\(]?\s*(\d\d\d)\s*[\]\}\)]?\s*', self.locality_parts['locality'], re.IGNORECASE)
        if results and results.group(1):
            self.locality_parts['locality'] = self.locality_parts['locality'].replace(results.group(0), '')
            self.locality_parts['farm_number'] = results.group(1)

        # If anything has changed in the locality string after this then it is a farm
        if temp != self.locality_parts['locality']:
            self.feature_type = self.FARM

            # I guess will add more feature types in here


@receiver(post_init, sender=LocalityName)
def post_init(sender, instance, **kwargs):
    # We are going to try and split it apart, so init an empty dict for the json field
    instance.locality_parts = {'locality': instance.locality_name}

    # Removes the superfluous strings and standardises the language
    instance._clean_locality()
    instance._get_directions()
    instance._set_feature_type()
    instance._get_lat_long_dms()
    instance._get_lat_long_dd()


class LocalityDate(models.Model):
    """
    A locality might have several dates associated with it
    """
    locality_name = models.ForeignKey(LocalityName)
    date = models.DateField(null=True, blank=True)


class GeoReference(models.Model):
    locality_name = models.ForeignKey(LocalityName)
    geographical_position = models.ForeignKey(GeographicalPosition, null=True, blank=True)
    user = models.ForeignKey(User)
    group_id = models.CharField(max_length=50)
    unique_id = models.CharField(max_length=50)
    created_on = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(max_length=50)

    # Potential locations - this is just a load of geojson
    potential_geographical_positions = JSONField(null=True, blank=True)

    def get_absolute_url(self):
        return reverse('georeference', args=[self.id])

    def auto_geolocate(self):
        # Initialize as a blank list if we don't start with any potential geo locations
        if not self.potential_geographical_positions:
            self.potential_geographical_positions = []
        else:
            ps = self.potential_geographical_positions
            self.potential_geographical_positions = []
            for gl in GeoJSONDeserializer(stream_or_string=ps,
                                          model_name='website.GeographicalPosition',
                                          geometry_field='point'):
                self.potential_geographical_positions.append(gl.object)

        # Sometimes during the locality cleaning process we will have uncovered a lat/long if so add that
        if 'lat' in self.locality_name.locality_parts and 'long' in self.locality_name.locality_parts:
            self.potential_geographical_positions.append(GeographicalPosition(point=Point(self.locality_name.locality_parts['long'],
                                                                        self.locality_name.locality_parts['lat'])))

        # Try and geolocate from our own database

        # Try and geolocate from google/other dbs
        self._geolocate_using_remote_db()

        # If we've managed to uncover anything then return it
        if self.potential_geographical_positions:
            self.potential_geographical_positions = serialize('custom_geojson', self.potential_geographical_positions, geometry_field='point')

    def _geolocate_using_remote_db(self):
        google_geolocator = GoogleV3()
        try:
            if 'province' in self.locality_name.locality_parts:
                results = google_geolocator.geocode(query=self.locality_name.locality_parts['locality'] + ', ' +
                                                          self.locality_name.locality_parts['province'],
                                                    region='za')
            else:
                results = google_geolocator.geocode(query=str(self.locality_name.locality_parts['locality']), region='za')

            # Has it actually managed to find coords beyond province level? and are we in the right country?
            country = ''
            for address_component in results.raw['address_components']:
                if address_component['types'] == ['country', 'political']:
                    country = address_component['short_name']

            # if str(results) != self.locality_parts['province'] + ", South Africa" and country == 'ZA':
            if "South Africa" and country == 'ZA':
                lat = results.raw['geometry']['location']['lat']
                long = results.raw['geometry']['location']['lng']
                # We are finding the difference in x and y between a point (i.e., x degrees)
                # self.notes = "Google maps API geolocates this as: " + results.raw['geometry']['location_type'] + \
                # " - distance from original qds = " + self._get_km_distance_from_two_points(self.lat, self.long)
                # TODO add in llres

                location = GeographicalPosition(point=Point(long, lat), origin=GeographicalPosition.GOOGLE)
                self.potential_geographical_positions.append(location)
        except AttributeError as e:
            print("Google maps could not find :" + str(self.locality_name.locality_parts['locality']) + ' gives error : ' + str(
                sys.exc_info()))
        except:
            print("ANOTHER ERROR occurred when looking up in google " + str(sys.exc_info()))
