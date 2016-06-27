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
    LOCALITY_STRING = 'LS'
    UNKNOWN = 'UN'
    origin_choices = (
        (USER, 'User'),
        (GOOGLE, 'Google'),
        (INPUT, 'Input'),
        (UNKNOWN, 'Unknown'),
        (LOCALITY_STRING, 'Derived from locality string')
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

    def clean_locality(self):
        # We are going to try and split it apart, so init an empty dict for the json field
        self.locality_parts = {'locality': self.locality_name.lower()}

        # Removes the superfluous strings and standardises the language
        self._get_lat_long_dms()
        self._get_lat_long_dd()
        self._get_altitude()
        self._standardise_language()
        self._get_directions()
        self._get_nearby()
        self._set_feature_type()

    def _get_lat_long_dms(self):
        # E.g. 29°58'51.5's 17°33'04.9'e
        regex = r'\s+([1-5]\d)°(\d\d)\'(\d\d(\.\d+)?)\'?s[\s:,]?\s*([1-5]\d)°(\d\d)\'(\d\d(\.\d+))?\'?e?'
        match = re.search(regex, str(self.locality_parts['locality']))

        # If this has not provided a match then try again
        if not match:
            regex = '\s[sS][\s\.](\d\d)[\s\.d](\d\d)[\s\.m](\d\d)(\.\d+)?s?\s*,?\s*[eE][\s\.](\d\d)[\s\.d](\d\d)[\s\.m](\d\d)(\.\d+)?s?\s'
            match = re.search(regex, str(self.locality_parts['locality']))

        # Finally if we have a match, do the conversion
        if match:
            south = {'degrees': float(match.group(1)), 'minutes': float(match.group(2)),
                     'seconds': float(match.group(3))}
            east = {'degrees': float(match.group(5)), 'minutes': float(match.group(6)),
                    'seconds': float(match.group(7))}
            lat = south['degrees'] + south['minutes'] / 60 + south['seconds'] / 3600
            long = east['degrees'] + east['minutes'] / 60 + east['seconds'] / 3600

            # Add the negative sign if necessary onto latitude
            if lat > 0:
                lat = lat * -1

            # Remove from the locality string
            self.locality_parts['locality'] = re.sub(regex, '', str(self.locality_parts['locality']))
            self.locality_parts['lat'] = lat
            self.locality_parts['long'] = long

    def _get_lat_long_dd(self):
        # See if it contains decimal degrees in the string itself
        regex = r'(-?[1-4]\d\.[0-9]+)\s*°?\s*s?[;\:,]?\s+(-?[1-4]\d\.[0-9]+)\s*°?\s*e?'
        match = re.search(regex, str(self.locality_parts['locality']))
        #   import pdb; pdb.set_trace()
        if match:
            lat = float(match.group(1))
            long = float(match.group(2))

            # Add the negative sign if necessary onto latitude
            if lat > 0:
                lat = lat * -1

            # Remove from the locality string
            self.locality_parts['locality'] = re.sub(regex, '', str(self.locality_parts['locality']))

            # Just be aware that we assume here that there is no lat/long in here
            self.locality_parts['lat'] = lat
            self.locality_parts['long'] = long

    def _standardise_language(self):
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
             'regex': [r'\s+(betwixt|twixt|tween|btwn\.?|betwn\.?)']},
            {'replace': '',
             'regex': [r'^collected\s+(from|in|on)?\s*', r'\s+along', r'\s+the(?=\s+)']},
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
                temp = re.sub(reg, '', self.locality_parts['locality'])
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

    def clean_string(self, s):
        # Excessive full stops
        s = re.sub(r'\s*\.\s*\.+\s*', '', s)
        s = re.sub(r'\s*,\s*,+\s*', '', s)
        s = re.sub(r'\s*:\s*:+\s*', '', s)
        s = re.sub(r'\s*;\s*;+\s*', '', s)
        s = re.sub(r'[\.,;:]$', '', s)
        s = re.sub(r'^[\.,;:]', '', s)
        return s.strip()

    def _get_directions(self):
        # Standardise measurement units
        measurement_units = {'miles': ['miles', 'mile', 'mi'],
                             'yards': ['yard', 'yards'],
                             'kilometers': ['km', 'kmeters', 'kmetres', 'kilometers', 'kmeter', 'kms', 'kmetre',
                                            'kilometer'],
                             'meters': ['m', 'meters', 'metres', 'meter', 'metre', 'ms'],
                             'feet': ['ft', 'feet']}

        # Loop through all of the possible measurement variations
        for measurement_unit, variations in measurement_units.items():
            for variation in variations:
                # Looking for 23.5 kmeters, 1,2 mi, 234,6 kms, etc
                regex = '^(.*?)(about|approx.?)?[\s+,]±?\s*(\d+[,\.]?\s*\d*)\s*(' + variation + ')\.?\s+(.*)$'

                # Find matches
                match = re.search(regex, self.locality_parts['locality'])
                if match:
                    # Convert the distance string to a float, to do this replace the , with . for decimal points
                    km_distance = float(re.sub(r'\s+', '', match.group(3).replace(',', '.')))

                    # Do some conversion for the different measurement units - we standardise to km
                    if measurement_unit == 'miles':
                        km_distance *= 1.60934
                    elif measurement_unit == 'meters':
                        km_distance *= 0.001
                    elif measurement_unit is 'feet':
                        km_distance *= 0.0003048
                    elif measurement_unit is 'yards':
                        km_distance *= 0.0009144

                    # Save the km distance
                    self.locality_parts['km_distance'] = km_distance

                    # Save the actual locality bit, everything before the distance should be the locality and
                    # Everything after should be greater locality
                    self.locality_parts['locality'] = self.clean_string(match.group(1))
                    self.locality_parts['place_measured_from'] = self.clean_string(match.group(5))

                    # Break out of both loops, we've found the distance/measurements
                    break

        if 'place_measured_from' in self.locality_parts:
            # Look for bearings, keep track of the ones we need to remove and get rid of them afterwards
            bearings_matches = {'south': ['south', 's', 'se', 'sw', 'south-east', 'southeast', 'south-west', 'southwest'],
                                'north': ['north', 'n', 'ne', 'nw', 'north-east', 'northeast', 'north-west', 'northwest'],
                                'east': ['east', 'e', 'se', 'ne', 'south-east', 'southeast', 'north-east', 'northeast'],
                                'west': ['west', 'w', 'sw', 'nw', 'south-west', 'southwest', 'north-west', 'northwest']}

            self.locality_parts['bearings'] = []
            strings_to_remove = set()  # apparently keeps unique values only
            for bearing, match_list in bearings_matches.items():
                for match in match_list:
                    regex = '(^|\s+)(due\s+)?(' + match + ')\.?(\s|of|$)'
                    match = re.search(regex, self.locality_parts['place_measured_from'])
                    if match:
                        self.locality_parts['bearings'].append(bearing)
                        strings_to_remove.add(regex)
                    '''temp = re.sub(regex, '', self.locality_parts['place_measured_from'])
                    if temp is not self.locality_parts['place_measured_from']:
                        self.locality_parts['bearings'].append(proper_name)
                        strings_to_remove.add(regex)'''
            if not self.locality_parts['bearings']:
                del self.locality_parts['bearings']

            # Remove all of the applicable bearings
            for regex in strings_to_remove:
                self.locality_parts['place_measured_from'] = re.sub(regex, '', self.locality_parts['place_measured_from'])

            # Now we might have 6km from cape town NE towards Worcester
            from_regex = r'(^|\s+)(of|fro?m|van)'
            regex = from_regex + r'(.+?)\s+(to|towards?|na)\s+(.+)$'
            match = re.search(regex, self.locality_parts['place_measured_from'])
            if match:
                self.locality_parts['place_measured_from'] = match.group(3)
                self.locality_parts['place_measured_towards'] = match.group(5)

            # We might also have just worcestor, 6km NE from cape town
            regex = r'\s+(of|fro?m|van)\s+'
            self.locality_parts['place_measured_from'] = re.sub(from_regex, '', self.locality_parts['place_measured_from'])

    def _get_nearby(self):
        regex = '\s+(between)(.+?)(and|&)([^\.]+)'
        match = re.search(regex, self.locality_parts['locality'])
        if match:
            self.locality_parts['between'] = [match.group(2), match.group(4)]
            self.locality_parts['locality'] = re.sub(regex, '', self.locality_parts['locality'])

        # Note that we already standardised nearby & between variations in standardise_language
        regex = '\s+nearby\s*([^.,;:]+)'
        match = re.search(regex, self.locality_parts['locality'])
        if match:
            self.locality_parts['nearby'] = match.group(1)
            self.locality_parts['locality'] = re.sub(regex, '', self.locality_parts['locality'])

    def _get_altitude(self):
        regex = r'alt(itude)?[:;\s]\s*(\d+)\s*m?'
        match = re.search(regex, self.locality_parts['locality'])
        if match:
            self.locality_parts['altitude_m'] = match.group(2)
            self.locality_parts['locality'] = re.sub(regex, '', self.locality_parts['locality'])

    def _set_feature_type(self):
        # Remove "in the / on the" for farms
        self.locality_parts['locality'] = re.sub(r'[\w\s]+?\s*[OoIi]n\s+(the\s+)?[Ff]arm\s*', 'Farm',
                                                 self.locality_parts['locality'])

        # Farm x, blah blah blah (we don't need the blah blah blah bit, so remove it and strip out the "Farm"
        temp = re.sub(r'^\s*Farm\s*(.+?),.+', "\g<1>", self.locality_parts['locality'])
        if temp is not self.locality_parts['locality']:
            self.locality_parts['feature_type'] = GeographicalPosition.FARM
            self.locality_parts['locality'] = temp

        # If this string contains three digits it's very likely to be a farm number
        # Alternate regex ^(([A-Za-z\-]+\s*?){1,4}),?\s?[\(\[\{]?(\d{3})[^\.].*$
        results = re.search('\s*[\[\{\(]?\s*(\d\d\d)\s*[\]\}\)]?\s*', self.locality_parts['locality'])
        if results and results.group(1):
            self.locality_parts['locality'] = self.locality_parts['locality'].replace(results.group(0), '')
            self.locality_parts['farm_number'] = results.group(1)
            self.locality_parts['feature_type'] = GeographicalPosition.FARM

        # If anything has changed in the locality string after this then it is a farm
        if temp != self.locality_parts['locality']:
            self.locality_parts['feature_type'] = GeographicalPosition.FARM


@receiver(post_init, sender=LocalityName)
def post_init(sender, instance, **kwargs):
    instance.clean_locality()

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
                if gl.object.origin == GeographicalPosition.INPUT:
                    self.potential_geographical_positions.append(gl.object)

        # Sometimes during the locality cleaning process we will have uncovered a lat/long if so add that
        if 'lat' in self.locality_name.locality_parts and 'long' in self.locality_name.locality_parts:
            self.potential_geographical_positions.append(GeographicalPosition(point=Point(self.locality_name.locality_parts['long'],
                                                                                          self.locality_name.locality_parts['lat']),
                                                                              origin=GeographicalPosition.LOCALITY_STRING))

        # Try and geolocate from our own database

        # Try and geolocate from google/other dbs
        self._geolocate_using_remote_db()

        # If we have multiple results with the same (roughly) point we need to make it just 1 point to display on map?

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
