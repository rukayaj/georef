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
from dateutil.relativedelta import relativedelta
from django.utils import formats
from django.db import connection


class Profile(models.Model):
    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    is_database = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class FeatureType(models.Model):
    type = models.CharField(max_length=50)

    def __str__(self):
        return self.type


class GeographicalPosition(models.Model):
    # Geographical location that has either a point or a polygon
    point = models.PointField(null=True, blank=True)
    polygon = models.PolygonField(null=True, blank=True)
    line = models.LineStringField(null=True, blank=True)
    altitude = models.IntegerField(null=True, blank=True)

    # The type or category of location
    feature_type = models.ForeignKey(FeatureType, null=True, blank=True)

    # Determines the resolution this point has been georeferenced to
    # No I think it is right. Georeference 1 "Slangkop" or 2 "Snakehead" should both lead to the same point and the
    # buffer should be associated with that point, if you can georef it finer then do it and change buffer + lat/long
    precision_m = models.IntegerField(null=True, blank=True, default=1000)

    # Any notes associated with this place
    notes = models.CharField(max_length=50, null=True, blank=True)

    def clean(self):
        # If it's not got a point or polygon or it's got a point and a polygon raise error
        if (not self.point and not self.polygon and not self.line) or (self.point and self.polygon):
            raise ValidationError('Either store line, point or polygon.')


class LocalityName(models.Model):
    # Keep a record of when this was added to the database
    created_on = models.DateTimeField(auto_now_add=True)

    # The main part of this model is the locality name e.g. "Cape Town"
    locality_name = models.TextField(help_text='The locality string', max_length=250)

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

        # Trim off extra full stops, commas, spaces, etc
        self.locality_parts['locality'] = self.clean_string(self.locality_parts['locality'])

        # We're also going to split up what's remaining by either , or . so we can break up our search
        self.locality_parts['split_localities'] = self.locality_parts['locality'].split('.')
        if len(self.locality_parts['split_localities']) == 1:
            self.locality_parts['split_localities'] = self.locality_parts['locality'].split(',')
        if len(self.locality_parts['split_localities']) == 1:
            self.locality_parts['split_localities'] = self.locality_parts['locality'].split(':')
        if len(self.locality_parts['split_localities']) == 1:
            self.locality_parts['split_localities'] = self.locality_parts['locality'].split(';')

        self.locality_parts['split_localities'] = [self.clean_string(x) for x in self.locality_parts['split_localities']
                                                   if self.clean_string(x) != '']

    def _get_lat_long_dms(self):
        south = False
        east = False

        # E.g. 29°58'51.5's 17°33'04.9'e
        regex = r'\s+([1-5]\d)°(\d\d)\'?([\d\.]+)["\']?\s*s[\s:;,]+([1-5]\d)°(\d\d)\'?([\d\.]+)["\']?\s*e?'
        match = re.search(regex, str(self.locality_parts['locality']))
        if match:
            south = {'degrees': float(match.group(1)), 'minutes': float(match.group(2)),
                     'seconds': float(0 if match.group(3) is None else match.group(3))}
            east = {'degrees': float(match.group(4)), 'minutes': float(match.group(5)),
                    'seconds': float(0 if match.group(6) is None else match.group(6))}
        else:
            regex = '\s[sS][\s\.](\d\d)[\s\.d](\d\d)[\s\.m](\d\d)(\.\d+)?s?\s*,?\s*[eE][\s\.](\d\d)[\s\.d](\d\d)[\s\.m](\d\d)(\.\d+)?s?\s'
            match = re.search(regex, str(self.locality_parts['locality']))

            if match:
                south = {'degrees': float(match.group(1)), 'minutes': float(match.group(2)),
                         'seconds': float(0 if match.group(3) is None else match.group(3))}
                east = {'degrees': float(match.group(5)), 'minutes': float(match.group(6)),
                        'seconds': float(0 if match.group(7) is None else match.group(7))}

        if south and east:
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
        # Get rid of all single quotes and double quotes, they cause havoc in the database
        self.locality_parts['locality'] = self.locality_parts['locality'].replace("'", '')
        self.locality_parts['locality'] = self.locality_parts['locality'].replace('"', '')

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
             'regex': [r'^collected\s+(from|in|on)?\s*', r'\s+along', r'\s+the(?=\s+)', 'lookout\s+over']}
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
        # Excessive punctuation
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

        # Sometimes we also have vague kind of "south of x" directions, in which case we want to remove the bearings...
        # So use s as a variable to hold one or the other, swap back in afterwards
        if 'place_measured_from' in self.locality_parts:
            s = self.locality_parts['place_measured_from']
        else:
            s = self.locality_parts['locality']

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
                match = re.search(regex, s)
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
            s = re.sub(regex, '', s)

        # Now we might have 6km from cape town NE towards Worcester
        from_regex = r'(^|\s+)(of|fro?m|van)'
        regex = from_regex + r'(.+?)\s+(to|towards?|na)\s+(.+)$'
        match = re.search(regex, s)
        if match:
            s = match.group(3)
            self.locality_parts['place_measured_towards'] = match.group(5)

        # We might also have just worcestor, 6km NE from cape town
        regex = r'\s+(of|fro?m|van)\s+'
        s = re.sub(from_regex, '', s)

        # Swap s back in
        if 'place_measured_from' in self.locality_parts:
            self.locality_parts['place_measured_from'] = s
        else:
            self.locality_parts['locality'] = s

    def _get_road(self):
        " on x road (to)?/ along x road/ on side of x road/ near x road"
        " x road"
        regex = r'\s+on\s+(.*?)road\s+(to)?'
        self.locality_parts['road'] = False

    def _get_nearby(self):
        regex = '\s+(between)(.+?)(and|&)([^\.,]+)'
        match = re.search(regex, self.locality_parts['locality'])
        if match:
            self.locality_parts['between'] = [match.group(2), match.group(4)]
            self.locality_parts['locality'] = re.sub(regex, '', self.locality_parts['locality'])

        # Note that we already standardised nearby & between variations in standardise_language
        regex = '\s+near\s+([^.,;:]+)'
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
             'regex': [r'\s+plaas\s+', r'(^|[\s,.])[oi]n\s+(the\s+)?farm\s*']},
            {'replace': 'forest',
             'regex': [r'\s+for\.']},
            {'replace': 'nature reserve',
             'regex': [r'\s+nat\.?\s+res\.?', r'\s+nat[\.\s]res[\.\s]', r'\s+n\.?\s?r\.?', r'nr\.']},
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

        # Farm x, blah blah blah (we don't need the blah blah blah bit, so remove it and strip out the "Farm"
        temp = re.sub(r'^\s*Farm\s*(.+?)[,.].+', "\g<1>", self.locality_parts['locality'])

        if temp is not self.locality_parts['locality']:
            self.locality_parts['feature_type'] = 'farm'
            self.locality_parts['locality'] = temp

        # If this string contains three digits it's very likely to be a farm number
        # Alternate regex ^(([A-Za-z\-]+\s*?){1,4}),?\s?[\(\[\{]?(\d{3})[^\.].*$
        results = re.search('\s*[\[\{\(]?\s*(\d\d\d)\s*[\]\}\)]?\s*', self.locality_parts['locality'])
        if results and results.group(1):
            # Remove from locality string
            self.locality_parts['locality'] = self.locality_parts['locality'].replace(results.group(0), '')

            # Add farm number
            self.locality_parts['farm_number'] = results.group(1)

            # Set as farm
            self.locality_parts['feature_type'] = 'farm'


@receiver(post_init, sender=LocalityName)
def post_init(sender, instance, **kwargs):
    if instance.pk is None:
        instance.clean_locality()


class GeoReference(models.Model):
    locality_name = models.ForeignKey(LocalityName)
    geographical_position = models.ForeignKey(GeographicalPosition, null=True, blank=True)
    author = models.ForeignKey(Profile)
    group_id = models.CharField(max_length=50, null=True, blank=True)
    unique_id = models.CharField(max_length=50, null=True, blank=True)
    locality_date = models.DateField(null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(max_length=50, null=True, blank=True)

    # Potential georeferences, these should only be ones where geographical_position is filled in
    potential_georeferences = models.ManyToManyField('self')

    def __str__(self):
        return str(self.locality_name) + ' by ' + str(self.author)

    def get_absolute_url(self):
        return reverse('georeference', args=[self.id])

    def get_serialized_geolocations(self):
        gps = self.potential_georeferences.get_queryset().select_related('geographical_position')
        return serialize('custom_geojson', gps, geometry_field='point')

    def add_potential_georeference(self, lat, long, profile_name, locality_name=False, precision_m=False):
        # Geographical position
        point = Point(long, lat)
        gp, created = GeographicalPosition.objects.get_or_create(point=point)

        # Precision
        if precision_m:
            gp.precision_m = precision_m

        # Author profile
        profile = Profile.objects.get(name=profile_name)

        # Locality name
        if not locality_name:
            ln = self.locality_name
        else:
            ln, created = LocalityName.objects.get_or_create(locality_name=locality_name)

        # Georeference
        gr, created = GeoReference.objects.get_or_create(geographical_position=gp,
                                                         locality_name=ln,
                                                         author=profile)

        # Add it to list
        if gr not in self.potential_georeferences.values():
            self.potential_georeferences.add(gr)

    def auto_geolocate(self):
        # Reset
        self.potential_georeferences.remove()
        self.potential_georeferences.clear()

        # Sometimes during the locality cleaning process we will have uncovered a lat/long if so add that
        if 'lat' in self.locality_name.locality_parts and 'long' in self.locality_name.locality_parts:
            self.add_potential_georeference(long=self.locality_name.locality_parts['long'],
                                            lat=self.locality_name.locality_parts['lat'],
                                            profile_name='User input')

        # First, try and geolocate the unedited string
        self.geolocate(self.locality_name.locality_name, limit=5)

        # Geolocate the locality + province, automatically saving it to our potential_geographical_positions
        if 'province' in self.locality_name.locality_parts:
            for s in self.locality_name.locality_parts['split_localities']:
                self.geolocate(s + ', ' + self.locality_name.locality_parts['province'], limit=3)
        else:
            for s in self.locality_name.locality_parts['split_localities']:
                self.geolocate(s, limit=1)

        # Ok now if we have between then get the midpoint between those two points
        if 'between' in self.locality_name.locality_parts:
            self.geolocate(self.locality_name.locality_parts['between'][0], notes='(BETWEEN)')
            self.geolocate(self.locality_name.locality_parts['between'][1], notes='(BETWEEN)')

        if 'place_measured_from' in self.locality_name.locality_parts:
            # Get a point for the start/place measured from place
            self.geolocate(self.locality_name.locality_parts['place_measured_from'], notes='(MEASURED FROM)')

            # Otherwise we might have measured towards somewhere
            if 'place_measured_towards' in self.locality_name.locality_parts:
                self.geolocate(self.locality_name.locality_parts['place_measured_towards'], notes='(MEASURED TOWARDS)')

    def geolocate(self, name, notes='', limit=2):
        # First try our own database:
        georefs = list(self._geolocate_database(name, limit=limit))
        for gr in georefs:
            if gr not in self.potential_georeferences.values():
                self.potential_georeferences.add(gr)

        # Then try external ones
        self._geolocate_google(name)
        self._geolocate_nominatim(name + ', South Africa')

        return len(georefs)

    def _geolocate_database(self, name, limit):
        # See if it's contained within something
        contains = LocalityName.objects.filter(locality_name__icontains=name)[:limit]

        # Uses levenshtein https://www.postgresql.org/docs/9.1/static/fuzzystrmatch.html
        # levenshtein(text source, text target, int ins_cost, int del_cost, int sub_cost) returns int
        # High substitute cost, low insert/delete cost 1, 1, 20 to find strings within strings
        # See also http://www.postgresonline.com/journal/archives/158-Where-is-soundex-and-other-warm-and-fuzzy-string-things.html
        ins_cost = 3
        del_cost = 5
        sub_cost = 9
        if ('fontein' in name or 'berg' in name or 'kloof' in name) and ' ' not in name:
            ins_cost = 13
            del_cost = 13
            sub_cost = 5
            print('penalising ' + name)
        looks_like = LocalityName.objects.raw(
            'select * from website_localityname where levenshtein(locality_name, %s, %s, %s, %s) <= 18 '
            'order by levenshtein(locality_name, %s, %s, %s, %s) limit %s',
            [name, ins_cost, del_cost, sub_cost, name, ins_cost, del_cost, sub_cost, limit])

        # http://www.informit.com/articles/article.aspx?p=1848528
        # Based on https://github.com/django/django/pull/4825#issuecomment-218737831 using metaphone
        # Let's be a bit cleverer and try and get the best matches we can
        # Open a connection to the database, and loop through a few times to get max 5 matches
        count = 6
        prev_count = 6
        metaphone_penalty = 4
        cursor = connection.cursor()
        while count > 5 and count != prev_count:
            sql = 'SELECT COUNT(*) FROM website_localityname WHERE metaphone(locality_name, %s) = metaphone(%s, %s)'
            try:
                cursor.execute(sql, [metaphone_penalty, name, metaphone_penalty])
            except:
                import pdb; pdb.set_trace()
            row = cursor.fetchone()
            prev_count = count
            count = row[0]
            metaphone_penalty += 1
            print('metaphone penalty ' + str(metaphone_penalty) + ' / count ' + str(count))

        # Close connection to database
        cursor.close()

        # If we got no results at all then go back up 1
        if count == 0:
            metaphone_penalty -= 1

        # Using the metaphone_penalty derived from the while loop, make our query
        sounds_like = LocalityName.objects.raw('select * from website_localityname where '
                                               'metaphone(locality_name, %s) = metaphone(%s, %s) limit %s',
                                               [metaphone_penalty, name, metaphone_penalty, limit])

        # Compile into 1 list
        matches = []
        for item in looks_like:
            if item not in matches:
                matches.append(item)
        for item in sounds_like:
            if item not in matches:
                matches.append(item)
        for item in contains:
            if item not in matches:
                matches.append(item)

        # Get the goereference objects and add any notes
        georefs = GeoReference.objects.filter(locality_name__in=matches).exclude(geographical_position__isnull=True).\
            distinct('locality_name', 'geographical_position')
        #import pdb; pdb.set_trace()
        return georefs

    def _geolocate_nominatim(self, string):
        g = Nominatim(timeout=30)
        results = g.geocode(query=string, exactly_one=True)
        if results and results[0]:
            self.add_potential_georeference(long=results.longitude,
                                            lat=results.latitude,
                                            profile_name='OpenStreetMap',
                                            locality_name=results.address)

    def _geolocate_google(self, string):
        g = GoogleV3()
        try:
            results = g.geocode(string, region='za')

            # Has it actually managed to find coords beyond province level? and are we in the right country?
            country = ''
            for address_component in results.raw['address_components']:
                if address_component['types'] == ['country', 'political']:
                    country = address_component['short_name']

            if country == 'ZA':
                # Get geographical position
                coords = results.raw['geometry']['location']
                ac = results.raw['address_components'][0]
                self.add_potential_georeference(long=coords['lng'],
                                                lat=coords['lat'],
                                                profile_name='Google',
                                                locality_name=ac['short_name'])

        except AttributeError as e:
            print("Google - not found: " + string + ' gives error : ' + str(sys.exc_info()))
            return False


