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
from django.contrib.gis.geos import Point, GeometryCollection, LineString
# Google maps geolocating API - https://github.com/geopy/geopy
from geopy.geocoders import GoogleV3, GeocodeFarm, Nominatim
from django.db.models.signals import post_init
from django.dispatch import receiver
from django.core.serializers import serialize
from django.contrib.auth.models import User
from djgeojson.serializers import Deserializer as GeoJSONDeserializer
from geopy.distance import distance, VincentyDistance
import math


class GeographicalPosition(models.Model):
    # Geographical location that has either a point or a polygon
    point = models.PointField(null=True, blank=True)
    polygon = models.PolygonField(null=True, blank=True)
    line = models.LineStringField(null=True, blank=True)
    altitude = models.IntegerField(null=True, blank=True)

    # The type of location
    TOWN = 'TO'
    ROAD = 'RO'
    MOUNTAIN = 'MO'
    RAILWAY = 'RA'
    FARM = 'FA'
    PARK = 'PA'
    BETWEEN = 'BE'
    MEASURED = 'ME'
    UNKNOWN = 'UN'
    feature_type_choices = (
        (TOWN, 'Town'),
        (ROAD, 'Road'),
        (MOUNTAIN, 'Mountain'),
        (RAILWAY, 'Railway'),
        (FARM, 'Farm'),
        (PARK, 'Park'),
        (MEASURED, 'Measurement from a place'),
        (BETWEEN, 'Between two places'),
        (UNKNOWN, 'Unknown')
    )
    feature_type = models.CharField(max_length=2, choices=feature_type_choices, default=UNKNOWN)

    # Determines the resolution this point has been georeferenced to
    # No I think it is right. Georeference 1 "Slangkop" or 2 "Snakehead" should both lead to the same point and the
    # buffer should be associated with that point, if you can georef it finer then do it and change buffer + lat/long
    precision = models.IntegerField(null=True, blank=True)

    # Origin of the point/polygon
    USER = 'US'
    GAZETTEER = 'GA'
    GOOGLE = 'GO'
    GEOCODEFARM = 'GE'
    NOMINATIM = 'NO'
    INPUT = 'IN'
    LOCALITY_STRING = 'LS'
    RQIS = 'RQ'
    ROADS = 'RO'
    UNKNOWN = 'UN'
    origin_choices = (
        (USER, 'User'),
        (GOOGLE, 'Google'),
        (GAZETTEER, 'SANBI gazetteer'),
        (GEOCODEFARM, 'Geocode farm'),
        (NOMINATIM, 'Nominatim'),
        (INPUT, 'Input'),
        (RQIS, 'South Africa 1:500 000 Rivers'),
        (ROADS, 'Official list of roads'),
        (UNKNOWN, 'Unknown'),
        (LOCALITY_STRING, 'Derived from locality string')
    )
    origin = models.CharField(max_length=2, choices=origin_choices, default=UNKNOWN)

    notes = models.CharField(max_length=50, null=True, blank=True)

    def clean(self):
        # If it's not got a point or polygon or it's got a point and a polygon raise error
        if (not self.point and not self.polygon and not self.line) or (self.point and self.polygon):
            raise ValidationError('Either store line, point or polygon.')


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
        self._get_province()
        self._get_directions()
        self._get_nearby()
        self._get_feature_type()

        # Do we want to split up places in the string if possible?
        phrases = [
            'at foot of',
            'along the top of',
            'at the bottom of',
            'at the mouth of',
            'nearby'
        ]

        self.locality_parts['locality'] = self.clean_string(self.locality_parts['locality'])

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
                     'seconds': float(0 if match.group(3) is None else match.group(3))}
            east = {'degrees': float(match.group(5)), 'minutes': float(match.group(6)),
                    'seconds': float(0 if match.group(7) is None else match.group(7))}
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
        # A simple attempt to try and standardise the language a bit, especially the afrikaans
        standardise_language = [
            {'replace': 'near',
             'regex': [r'\s+nr\.?(?=\s+)', r'\s+naby(?=\s+)', r'nearby', r'above', r'below', r'behind',
                       r'\s+in\s*front(\s+of)?', r'\s+ne(ar|xt|arby)\s+to', r'\s+skirting']},
            {'replace': 'between',
             'regex': [r'\s+(betwixt|twixt|tween|btwn\.?|betwn\.?)']},
            {'replace': 'road',
             'regex': [r'\s+(pad|rd\.|rd|weg)(?=\s+)']},
            {'replace': 'on',
             'regex': [r'\s+op(?=\s+)']},
            {'replace': 'the',
             'regex': [r'\s+die(?=\s+)']},
            {'replace': '',
             'regex': [r'^collected\s+(from|in|on)?\s*', r'\s+along', r'\s+the(?=\s+)']}
        ]

        # Run a place through it
        for item in standardise_language:
            for reg in item['regex']:
                self.locality_parts['locality'] = re.sub(reg, ' ' + item['replace'], self.locality_parts['locality'],
                                                         flags=re.IGNORECASE)

    def _get_province(self):
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

    def clean_string(self, s):
        # Excessive full stops
        s = re.sub(r'\s*\.\s*\.+\s*', '', s)
        s = re.sub(r'\s*,\s*,+\s*', '', s)
        s = re.sub(r'\s*:\s*:+\s*', '', s)
        s = re.sub(r'\s*;\s*;+\s*', '', s)
        s = re.sub(r'[\.,;:]$', '', s)
        s = re.sub(r'^[\.,;:]', '', s)
        s = re.sub(r'[,.:;]{2,}', ',', s)
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
                # regex = '^(.*?)(about|approx.?)?[\s+,]±?\s*(\d+[,\.]?\s*\d*)\s*(' + variation + ')\.?\s+(.*)$'
                regex = '(about|approx\.?|±)?\s*(\d+[,\.]?\s*\d*)\s*(' + variation + ')\.?\s+(.+$)'

                # Find matches
                match = re.search(regex, self.locality_parts['locality'])
                if match:
                    # Convert the distance string to a float, to do this replace the , with . for decimal points
                    km_distance = float(re.sub(r'\s+', '', match.group(2).replace(',', '.')))

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
                    self.locality_parts['locality'] = self.clean_string(re.sub(regex, '', self.locality_parts['locality']))
                    if not self.locality_parts['locality'] or self.locality_parts['locality'] is None:
                        self.locality_parts['locality'] = self.clean_string(match.group(4))
                    self.locality_parts['place_measured_from'] = self.clean_string(match.group(4))

                    # Break out of both loops, we've found the distance/measurements
                    break

        if 'place_measured_from' in self.locality_parts:
            # Look for bearings, keep track of the ones we need to remove and get rid of them afterwards
            bearings_matches = {
                'south': ['south', 's', 'se', 'sw', 'south-east', 'southeast', 'south-west', 'southwest'],
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
                self.locality_parts['place_measured_from'] = re.sub(regex, '',
                                                                    self.locality_parts['place_measured_from'])

            # Now we might have 6km from cape town NE towards Worcester
            from_regex = r'(^|\s+)(of|fro?m|van)'
            regex = from_regex + r'(.+?)\s+(to|towards?|na)\s+(.+)$'
            match = re.search(regex, self.locality_parts['place_measured_from'])
            if match:
                self.locality_parts['place_measured_from'] = match.group(3)
                self.locality_parts['place_measured_towards'] = match.group(5)

            # We might also have just worcestor, 6km NE from cape town
            regex = r'\s+(of|fro?m|van)\s+'
            self.locality_parts['place_measured_from'] = re.sub(from_regex, '',
                                                                self.locality_parts['place_measured_from'])

    def _get_road(self):
        " on x road (to)?/ along x road/ on side of x road/ near x road"
        " x road"
        regex = r'\s+on\s+(.*?)road\s+(to)?'
        self.locality_parts['road'] = False


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

    def _get_feature_type(self):
        # Standardise feature names
        feature_types = [
            {'replace': 'farm',
             'regex': [r'\s+plaas\s+', r'[\w\s]+?\s*[oi]n\s+(the\s+)?farm\s*']},
            {'replace': 'forest',
             'regex': [r'\s+for\.']},
            {'replace': 'nature reserve',
             'regex': [r'\s+nat\.?\s+res\.?', r'\s+n\.?\s?r\.?', r'nr\.']},
            {'replace': 'game reserve',
             'regex': [r'\s+game\s+res\.']},
            {'replace': 'reserve',
             'regex': [r'\s+res\.']},
            {'replace': 'national park',
             'regex': [r'\s+nat\.?\s+park\.?', r'\s+n(at)?\.?\s?p(ark)?\.?\s+']},
            {'replace': 'district',
             'regex': [r'\s+dist(\.|\s+)', r'\s+div(\.|\s+)']},
            {'replace': 'station',
             'regex': [r'\s+sta(\.|\s+)']},
            {'replace': 'mountain',
             'regex': [r'\s+mn?t(\.|\s+)']},
            {'replace': 'river',
             'regex': [r'\s+rvr(\.|\s+)']}
        ]

        # Run a place through it
        for item in feature_types:
            for reg in item['regex']:
                self.locality_parts['locality'] = re.sub(reg, ' ' + item['replace'], self.locality_parts['locality'])

            #re.search(item['replace'], self.locality_parts['locality'])

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
    user = models.ForeignKey(User, null=True, blank=True)
    group_id = models.CharField(max_length=50)
    unique_id = models.CharField(max_length=50)
    created_on = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(max_length=50)

    # Potential locations - this is just a load of geojson
    potential_geographical_positions = JSONField(null=True, blank=True)

    def get_absolute_url(self):
        return reverse('georeference', args=[self.id])

    def auto_geolocate(self):
        # Initialize as a blank list if we don't start with any potential geographical positions
        if not self.potential_geographical_positions:
            self.potential_geographical_positions = []
        else:
            ps = self.potential_geographical_positions
            self.potential_geographical_positions = []
            for gl in GeoJSONDeserializer(stream_or_string=ps,
                                          model_name='website.GeographicalPosition',
                                          geometry_field='point'):
                # Add any pre-existing geographical positions which are 'input' types i.e. came in bulk form
                if gl.object.origin == dict(GeographicalPosition.origin_choices).get(GeographicalPosition.INPUT):
                    self.potential_geographical_positions.append(gl.object)

        # Sometimes during the locality cleaning process we will have uncovered a lat/long if so add that
        if 'lat' in self.locality_name.locality_parts and 'long' in self.locality_name.locality_parts:
            self.potential_geographical_positions.append(
                GeographicalPosition(point=Point(self.locality_name.locality_parts['long'],
                                                 self.locality_name.locality_parts['lat']),
                                     origin=GeographicalPosition.LOCALITY_STRING,
                                     notes='Taken from lat/long in locality string'))

        # Geolocate!

        # From our database (inc the gazetteer)
        matched_georeferences = self._search_for_locality(self.locality_name.locality_parts['locality'])
        for m in matched_georeferences:
            m.geographical_position.notes = m.locality_name.locality_parts['locality'].title()
            self.potential_geographical_positions.append(m.geographical_position)

        # From remote dbs, format string accordingly
        if 'province' in self.locality_name.locality_parts:
            string = self.locality_name.locality_parts['locality'] + ', ' + self.locality_name.locality_parts['province']
        else:
            string = self.locality_name.locality_parts['locality']
        self.geolocate_google(string)
        self._geolocate_nominatim(string + ', South Africa')

        # Ok now if we have between then get the midpoint between those two points
        if 'between' in self.locality_name.locality_parts:
            geo_a = self._get_best_geographical_position(self.locality_name.locality_parts['between'][0])
            geo_b = self._get_best_geographical_position(self.locality_name.locality_parts['between'][1])
            line = LineString(geo_a.point, geo_b.point)
            self.potential_geographical_positions.append(GeographicalPosition(point=line.centroid,
                                                                              origin=GeographicalPosition.LOCALITY_STRING,
                                                                              feature_type=GeographicalPosition.BETWEEN,
                                                                              notes='Between ' + self.locality_name.locality_parts['between'][0].strip() + ' and ' + self.locality_name.locality_parts['between'][1].strip()))

        if 'place_measured_from' in self.locality_name.locality_parts:
            # Get a point for the start/place measured from place
            start = self._get_best_geographical_position(self.locality_name.locality_parts['place_measured_from'])
            self.potential_geographical_positions.append(GeographicalPosition(point=start.point,
                                                                              origin=GeographicalPosition.LOCALITY_STRING,
                                                                              feature_type=GeographicalPosition.MEASURED,
                                                                              notes=start.notes + ' (start of measurement)'))

            # Check for bearings and distances
            if start and 'bearings' in self.locality_name.locality_parts and 'km_distance' in self.locality_name.locality_parts:
                # Convert to numbers for VincentyDistance 0 degrees is north, 180 is south
                degrees = self.get_bearings(self.locality_name.locality_parts['bearings'])

                # Use the `destination` method with a bearing of 0 degrees (which is north)
                # in order to go from point `start` 1 km to north.
                destination = VincentyDistance(kilometers=self.locality_name.locality_parts['km_distance'] * -1).destination(start.point, degrees)
                destination = Point(destination.latitude, destination.longitude)  # Why does this have to be swapped?
                self.potential_geographical_positions.append(GeographicalPosition(point=destination,
                                                                                  origin=GeographicalPosition.LOCALITY_STRING,
                                                                                  feature_type=GeographicalPosition.MEASURED,
                                                                                  notes=str(self.locality_name.locality_parts['km_distance']) + ' ' + ' from ' + start.notes))

            # Otherwise we might have measured towards somewhere
            if 'place_measured_towards' in self.locality_name.locality_parts:
                towards = self._get_best_geographical_position(self.locality_name.locality_parts['place_measured_towards'])
                self.potential_geographical_positions.append(GeographicalPosition(point=towards.point,
                                                                                  origin=GeographicalPosition.LOCALITY_STRING,
                                                                                  feature_type=GeographicalPosition.MEASURED,
                                                                                  notes=towards.notes + ' (end of measurement)'))
                if start and 'km_distance' in self.locality_name.locality_parts:
                    # Get the angle between the start and end points
                    radian = math.atan((start.point.y - towards.point.y) / (start.point.x - towards.point.x))
                    degrees = abs(radian * 180 / math.pi)

                    w = start.point.x > towards.point.x
                    e = start.point.x < towards.point.x
                    n = start.point.y < towards.point.y
                    s = start.point.y > towards.point.y

                    if n and w:
                        degrees = degrees + 270
                    elif n and e:
                        degrees = 90 - degrees
                    elif s and w:
                        degrees = 270 - degrees
                    elif s and e:
                        degrees = 90 + degrees

                    # distance = self.locality_name.locality_parts['km_distance']
                    # lat = start.point.y + (distance * math.sin(degrees))
                    # long = start.point.x + (distance * math.cos(degrees))
                    # destination = Point(long, lat)

                    # Measure the distance along that angle

                    destination = VincentyDistance(kilometers=self.locality_name.locality_parts['km_distance']).destination(start.point, degrees)
                    destination = Point(destination.latitude, destination.longitude)  # Why does this need to be swapped?
                    self.potential_geographical_positions.append(GeographicalPosition(point=destination,
                                                                                      origin=GeographicalPosition.LOCALITY_STRING,
                                                                                      feature_type=GeographicalPosition.MEASURED,
                                                                                      notes=str(self.locality_name.locality_parts['km_distance'])
                                                                                            + ' ' + ' from ' + start.notes + ' towards ' + towards.notes))
                elif start and 'km_distance' not in self.locality_name.locality_parts:
                    # Otherwise if we don't have a distance, just get the midpoint
                    line = LineString(start.point, towards.point)
                    self.potential_geographical_positions.append(GeographicalPosition(point=line.centroid,
                                                                                      origin=GeographicalPosition.LOCALITY_STRING,
                                                                                      feature_type=GeographicalPosition.BETWEEN,
                                                                                      notes='Midpoint between ' + start.notes + ' and ' +
                                                                                            towards.notes))

        # If we have multiple results with the same (roughly) point we need to make it just 1 point to display on map?

        # If we've managed to uncover anything then return it
        if self.potential_geographical_positions:
            self.potential_geographical_positions = serialize('custom_geojson', self.potential_geographical_positions,
                                                              geometry_field='point')

    def get_bearings(self, bs):
        degrees = 0
        operator = 1 if 'east' in bs else -1
        ns_count = bs.count('north')

        # If your bearing is south and you move further east you subtract from 180, westward you add (opposite in north)
        if 'south' in bs:
            degrees = 180
            operator *= -1
            ns_count = bs.count('south')

        # Count how many times you have to move east/west
        ew_count = bs.count('west') if 'west' in bs else bs.count('east')
        if ew_count:
            # Either add or subtract 45 degrees
            degrees += (45 * operator)
            if ew_count == 2:  # Not even going to think about more than 2
                degrees += ((45 / 2) * operator)

        # Count how many times you have to move north/south
        if ns_count == 2:
            degrees += ((45 / 2) * operator * -1)

        return degrees % 360

    def _get_best_geographical_position(self, name):
        georeference = self.geolocate_google(name, append=False)
        if georeference is not None:
            return georeference
        else:
            matched_georeferences = self._search_for_locality(name, exactly_one=True)
            if matched_georeferences:
                georeference = matched_georeferences[0]
                georeference.geographical_position.notes = str(georeference.locality_name)
                return georeference.geographical_position
            else:
                return False

    def _search_for_locality(self, name, exactly_one=False):
        # Uses levenshtein https://www.postgresql.org/docs/9.1/static/fuzzystrmatch.html
        # levenshtein(text source, text target, int ins_cost, int del_cost, int sub_cost) returns int
        # High substitute cost, low insert/delete cost 1, 1, 20 to find strings within strings
        # See also http://www.postgresonline.com/journal/archives/158-Where-is-soundex-and-other-warm-and-fuzzy-string-things.html
        looks_like = LocalityName.objects.raw(
            'select * from website_localityname where levenshtein(locality_name, %s, 1, 3, 8) <= 19 '
            'order by levenshtein(locality_name, %s, 1, 3, 8) limit 5',
            [name, name])

        # http://www.informit.com/articles/article.aspx?p=1848528
        # Based on https://github.com/django/django/pull/4825#issuecomment-218737831 using metaphone
        sounds_like = LocalityName.objects.raw('select * from website_localityname where metaphone(locality_name, 5) = metaphone(%s, 5) limit 5', [name])

        # Compile into 1 list
        matches = []
        for item in looks_like:
            if item not in matches:
                matches.append(item)
        for item in sounds_like:
            if item not in matches:
                matches.append(item)

        if exactly_one:
            return GeoReference.objects.filter(locality_name=matches[0]).exclude(geographical_position__isnull=True).distinct('locality_name', 'geographical_position')

        # Return only items which are georeferenced & which are distinct
        # TODO make it so that if there are a lot of georeferences pointing at the same point it prioritises those... how?
        return GeoReference.objects.filter(locality_name__in=matches).exclude(geographical_position__isnull=True).distinct('locality_name', 'geographical_position')

    def _geolocate_nominatim(self, string, append=True):
        g = Nominatim(timeout=30)
        try:
            results = g.geocode(query=string, exactly_one=True)
            if results and results[0]:
                gp = GeographicalPosition(point=Point(results.longitude, results.latitude), origin=GeographicalPosition.NOMINATIM)
                # Doesn't seem to throw an error if it doesn't find anything?
                if append:
                    self.potential_geographical_positions.append(gp)
                return gp
        except:
            print("Nominatim - error: " + str(sys.exc_info()))

    def _geolocate_geocode_farm(self, string, append=True):
        g = GeocodeFarm(timeout=30)
        try:
            results = g.geocode(query=string, exactly_one=True)
            coords = results['geocoding_results']['RESULTS'][0].coordinates
            gp = GeographicalPosition(point=Point(coords['longitude'], coords['latitude']), origin=GeographicalPosition.GEOCODEFARM)
            if append:
                self.potential_geographical_positions.append(gp)
            return gp
        except AttributeError as e:
            print("Geocodefarm - not found: " + string + ' gives error : ' + str(sys.exc_info()))
        except:
            print("Geocodefarm - error: " + str(sys.exc_info()))

    def geolocate_google(self, string, append=True):
        g = GoogleV3()
        try:
            results = g.geocode(string, region='za')

            # Has it actually managed to find coords beyond province level? and are we in the right country?
            country = ''
            for address_component in results.raw['address_components']:
                if address_component['types'] == ['country', 'political']:
                    country = address_component['short_name']

            if country == 'ZA':
                coords = results.raw['geometry']['location']
                gp = GeographicalPosition(point=Point(coords['lng'], coords['lat']), origin=GeographicalPosition.GOOGLE)
                if 'short_name' in results.raw['address_components'][0]:
                    gp.notes = results.raw['address_components'][0]['short_name']
                if append:
                    self.potential_geographical_positions.append(gp)
                return gp
        except AttributeError as e:
            print("Google - not found: " + string + ' gives error : ' + str(sys.exc_info()))
        except:
            print("Google - error: " + str(sys.exc_info()))
