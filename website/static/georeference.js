$(document).ready(function() {
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

  map.on('draw:created', function (e) {
    var type = e.layerType,
      layer = e.layer;

    if (type === 'marker') {
      layer.bindPopup('A popup!');
    }

    editableLayers.addLayer(layer);
  });

  $('.btn-process').click(function(event) {
    // Each time we click the button remove the previous layer (if there was one)
    if(typeof geojsonLayer != 'undefined') {
      map.removeLayer(geojsonLayer);
      editableLayers.clearLayers();
    }

    // Highlight the new row we're on
    $('tr.warning').removeClass('warning');
    $(this).parents('tr').addClass('warning');

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
            // Create the div for the popup content
            popupContent = $('<div>');

            // Create the button for actually submitting it as georeferenced
            var button = $('<button>').addClass('btn btn-warning btn-sm btn-georeference').html('Set as georeferenced point');

            // Add the origin/georeferencing source
            popupContent.append($('<strong>').append(feature.properties.origin));
            button.attr('data-source', feature.properties.origin);

            // Add the coordinates
            popupContent.append($('<br>'));
            popupContent.append(feature.geometry.coordinates);
            button.attr('data-coordinates', feature.geometry.coordinates);

            // Add the buffer if applicable
            if(feature.properties.buffer) {
                popupContent.append($('<br>'));
                popupContent.append('Resolution confidence: ' + feature.properties.buffer + 'm');
                button.attr('data-resolution', feature.properties.buffer);

                // Add the buffer to the map
                layer.on('click', function(e) {
                    L.circle([feature.geometry.coordinates[1], feature.geometry.coordinates[0]], feature.properties.buffer, {
                    'stroke': 0,
                    'fillColor': '#fff693'
                    }).addTo(map);
                });
            }

            // Create the click function for the button
            button.click(function() {
              // Send info to get saved into the database
              /*$.ajax({
                url: "script.php",
                method: "POST",
                data: { id : menuId },
                dataType: "html"
              });*/
            })

            // Add button to popupContent, quite tricky to figure this out, see
            // http://stackoverflow.com/questions/13698975/click-link-inside-leaflet-popup-and-do-javascript
            popupContent.append($('<br>'));
            popupContent = $(popupContent).append(button)[0];
        }

        layer.bindPopup(popupContent);
      }
    });

    // Add the layer to the map and zoom to it
    map.addLayer(geojsonLayer);
    map.fitBounds(geojsonLayer, {padding: [80, 80]});
  });

});