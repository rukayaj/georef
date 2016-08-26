from django.contrib.gis.serializers.geojson import Serializer as GeoJSONSerializer
from django.core.urlresolvers import reverse
from django.utils.encoding import smart_text


class Serializer(GeoJSONSerializer):
    # We have to override the handle_field method just slightly in order to make it display the user friendly choice
    # Taken from https://groups.google.com/forum/#!topic/django-users/u2L1_BAtFM0
    def handle_field(self, obj, field):
        if field.name == self.geometry_field:
            self._geometry = field._get_val_from_obj(obj)
        else:
            value = field._get_val_from_obj(obj)

            # If the object has a get_field_display() method, use it.
            display_method = "get_%s_display" % field.name
            if hasattr(obj, display_method):
                self._current[field.name] = getattr(obj, display_method)()
            # I added this else just to pass it to the generic handler
            else:
                super(Serializer, self).handle_field(obj, field)


    # http://stackoverflow.com/questions/5453237/override-django-object-serializer-to-get-rid-of-specified-model
    def end_object(self, obj):
        try:
            print(obj.geographical_position.precision_m)
        except:
            import pdb; pdb.set_trace()
        # We need to retrieve the locality_name and author
        additions = {'locality_name': str(obj.locality_name).replace("'", '').replace('"', ''),
                     'author': str(obj.author).replace("'", '').replace('"', ''),
                     'author_is_database': obj.author.is_database,
                     'pk': obj.pk,
                     'precision_m': obj.geographical_position.precision_m}
        self._current.update(additions)

        # We also need to set the geometry point for serialization
        if obj.geographical_position.polygon:
            self._geometry = obj.geographical_position.polygon
        else:
            self._geometry = obj.geographical_position.point

        # Super
        super(Serializer, self).end_object(obj)
