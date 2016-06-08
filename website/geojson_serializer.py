from django.contrib.gis.serializers.geojson import Serializer as GeoJSONSerializer


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
