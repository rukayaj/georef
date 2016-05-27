$(document).ready(function() {
  // Initialise map
  map = L.map('leaflet').setView([-29, 24.5], 5);
  L.tileLayer('http://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Map data &copy; 2013 OpenStreetMap contributors',
  }).addTo(map);

  $('.btn-process').click(function(event) {
    // Each time we click the button remove the previous layer (if there was one)
    if(typeof geojsonLayer != 'undefined') {
      map.removeLayer(geojsonLayer);
    }

    // Get the main set of georeferenced points and add to geojson layer
    georeferences = $.parseJSON($(this).attr('data-locations'));

    // Make it a list because we may add original point to it (see below)
    georeferences = [georeferences];

    // If there's an original point passed in from the HoT we need to add it too
    if($(this).attr('data-original-point')) {
      original_point = $.parseJSON($(this).attr('data-original-point'));
      georeferences.push(original_point);
    }

    // Create a geojson layer, see https://www.dartdocs.org/documentation/leaflet/0.0.1-alpha.4/leaflet.layer/GeoJSON/addData.html
    geojsonLayer = L.geoJson(georeferences, {
      /*pointToLayer: function(feature, latlng) {
          return new L.CircleMarker(latlng, {radius: 10, fillOpacity: 0.85});
      },*/
      onEachFeature: function (feature, layer) {
        popupContent = 'No information available.';
        if(feature.geometry && feature.properties && feature.properties.origin) {
            popupContent = '<strong>' + feature.properties.origin + '</strong><br>' + feature.geometry.coordinates;

            if(feature.properties.buffer) {
                popupContent += '<br>Resolution confidence: ' + feature.properties.buffer + 'm';
                layer.on('click', function(e) {
                    // Add the buffer to the map
                    L.circle([feature.geometry.coordinates[1], feature.geometry.coordinates[0]], feature.properties.buffer, {
                    'stroke': 0,
                    'fillColor': '#fff693'
                    }).addTo(map);
                });
            }
        }
        layer.bindPopup(popupContent);
      }
    });

    // Add the layer to the map and zoom to it
    map.addLayer(geojsonLayer);
    map.fitBounds(geojsonLayer, {padding: [80, 80]});

  });
});