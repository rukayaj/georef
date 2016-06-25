$(document).ready(function() {
  $('textarea').attr('rows', 3);

  // Initialise map
  map = L.map('leaflet').setView([-29, 24.5], 5); // , {drawControl: true}
  L.tileLayer('http://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Map data &copy; 2013 OpenStreetMap contributors',
  }).addTo(map);

  // Add leaflet draw
  // Initialise the FeatureGroup to store editable layers
  var editableLayers  = new L.FeatureGroup();
  map.addLayer(editableLayers);

  // Initialise the draw control and pass it the FeatureGroup of editable layers
  var drawControl = new L.Control.Draw({
    edit: {
      featureGroup: editableLayers, //REQUIRED!!
      remove: false
    },
    draw: {
      polyline: false,
      circle: false,
      rectangle: false
    }
  });
  map.addControl(drawControl);

  // Let people create manual points
  map.on('draw:created', function (e) {
    var type = e.layerType,
      layer = e.layer;

    if (type === 'marker') {
      // Make a copy of the template form (hidden in the HTML)
      var form = $('.template-form').clone();

      // Get the latlong for the layer
      var latLong = layer.getLatLng();
      $(form).find('h3 small').text(latLong.lat.toFixed(5) + ', ' + latLong.lng.toFixed(5));
      $(form).find('#id_point').val('SRID=4326;POINT (' + latLong.lng + ' ' + latLong.lat + ')');
      //$(form).find('#id_point').val(latLong);

      form.removeClass('template-form');
      form.addClass('georef-form');
      form.show();

      layer.bindPopup(form.prop('outerHTML')).openPopup();
    }

    editableLayers.addLayer(layer);
  });

  // Add the measure control for areas
  var measureAreaControl = new L.control.measure();
  map.addControl(measureAreaControl);

  // Add the measure control for lines
  var measureControl = new L.Control.measureControl();
  map.addControl(measureControl);

  // Create a geojson layer, see https://www.dartdocs.org/documentation/leaflet/0.0.1-alpha.4/leaflet.layer/GeoJSON/addData.html
  geojsonLayer = L.geoJson(potential_geographical_positions, {
    /*pointToLayer: function(feature, latlng) { // Change marker according to input type
        return new L.CircleMarker(latlng, {radius: 10, fillOpacity: 0.85});
    },*/
    onEachFeature: function (feature, layer) {
      popupContent = 'No information available.';
      if(feature.geometry && feature.properties && feature.properties.origin) {
          // Make a copy of the template form (hidden in the HTML) and change the class and show it
          var form = $('.template-form').clone();
          form.removeClass('template-form');
          form.addClass('georef-form');
          form.show();

          // Set the heading
          $(form).find('.form-heading').text(feature.properties.origin);

          // Add in the coordinates
          var coords = feature.geometry.coordinates
          $(form).find('.form-coords').text(coords[1].toFixed(5) + ', ' + coords[0].toFixed(5));
          $(form).find('#id_point').val('SRID=4326;POINT (' + coords[0] + ' ' + coords[1] + ')');

          // Select the correct option
          $(form).find('#id_origin option').attr("selected", false);
          $(form).find('#id_origin option').filter(function() {
            return this.text == feature.properties.origin;
          }).attr("selected", true);

          // Prevent modification, this disabled must be removed before the form is actually submitted
          $(form).find('#id_origin').attr('disabled', true);

          // Add in the buffer if there is one, otherwise they must set it themselves
          if(feature.properties.buffer){
            $(form).find('#id_buffer').val(parseInt(feature.properties.buffer, 10));
            $(form).find('#id_buffer').attr('value', parseInt(feature.properties.buffer, 10));
            $(form).find('#id_buffer').attr('readonly', true);

            // Add the buffer to the map
            /*layer.on('click', function(e) {
                L.circle([feature.geometry.coordinates[1], feature.geometry.coordinates[0]], feature.properties.buffer, {
                'stroke': 0,
                'fillColor': '#fff693'
                }).addTo(map);
            });*/
          }

          // Bind the layer with the form
          layer.bindPopup(form.prop('outerHTML'));
      }
    }
  });

  // Add the layer to the map and zoom to it
  map.addLayer(geojsonLayer);
  map.fitBounds(geojsonLayer, {padding: [80, 80]});


});