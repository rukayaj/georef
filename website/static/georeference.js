  function georeferenceFunc(e) {
      console.log('hello');
      e.preventDefault();
      return false;
  }
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

  // Send info to get saved into the database
  /*$('.georeference-submit').click(function(e) {
    console.log('hello');
    e.preventDefault();
  });*/
  $('.submit-form').submit(function(e) {
    console.log('hello');
    console.log($(this).attr('action'));
    /*
    $.ajax({
      type: "POST",
      url: $(this).attr('action'),
      data: $(this).serialize(),
      success: function(data) {
        window.location = redirect_url;
      }
    });*/

    //$.ajax({ type: 'POST', url: $(this).attr('action'), data: $(this).serialize(), success: function(data) { window.location = redirect_url; }});
    console.log('hello');
    e.preventDefault();
  });

  function createPopup(lat, long, buffer) {
    var templateForm = $('.template-form');
    latLong = layer.getLatLng();
    $('.template-form h3 small').text(latLong.lat.toFixed(5) + ', ' + latLong.lng.toFixed(5));
    $('.template-form input.lat').val(latLong.lat);
    $('.template-form input.long').val(latLong.long);
    var form = templateForm.clone();
    form.removeClass('.template-form');
    form.addClass('.submit-form');
    return form;
    //$('<input>').attr({ type: 'hidden', id: 'lat', name: 'lat', value: lat}).appendTo(form);
    //$('<input>').attr({ type: 'hidden', id: 'long', name: 'long', value: long}).appendTo(form);
    //$('<input>').attr({ type: 'text', id: 'buffer', name: 'buffer', value: buffer}).appendTo(form);
  }

  // Let people create manual points
  map.on('draw:created', function (e) {
    var type = e.layerType,
      layer = e.layer;

    if (type === 'marker') {
      /*
      // Add the popup
      popupContent = $('<div>');

      // Create the button for actually submitting it as georeferenced
      var button = $('<button>').addClass('btn btn-warning btn-sm').html('Set as georeferenced point');

      // At some point here we need to change it to dynamic input
      popupContent.append($('<strong>').append('Map marker'));
      popupContent.append($('<br>'));
      button.attr('data-origin', 'INPUT');
      console.log(e);
      console.log(layer);
      console.log();
      // Add the coordinates
      latLong = layer.getLatLng();
      popupContent.append(latLong.lat.toFixed(5) + ', ' + latLong.lng.toFixed(5));
      button.attr('data-lat', latLong.lat);
      button.attr('data-long', latLong.lng);
      popupContent.append('<br>Resolution confidence:');
      var buffer = $('<input type="text" placeholder="E.g. 0.5">');


      // Create the click function for the button
      button.click(function() {
        console.log($(this).data());
        // Send info to get saved into the database
        $.ajax({
          url: georef_ajax_url,
          method: "POST",
          data: { 'content': $(this).data(), 'georeference_id': georeference_id, 'csrfmiddlewaretoken': csrf },
          dataType: "json"
        }).done(function(returned_data) {
          window.location = redirect_url;
        });
      })

      // Add button to popupContent, quite tricky to figure this out, see
      // http://stackoverflow.com/questions/13698975/click-link-inside-leaflet-popup-and-do-javascript
      popupContent.append($('<br>'));
      popupContent = $(popupContent).append(button)[0];
      layer.bindPopup(popupContent);
      */

      var latLong = layer.getLatLng();
      $('.template-form h3 small').text(latLong.lat.toFixed(5) + ', ' + latLong.lng.toFixed(5));
      $('.template-form input.lat').val(latLong.lat);
      $('.template-form input.long').val(latLong.long);
      var form = $('.template-form').clone();

      form.removeClass('template-form');
      form.addClass('georef-form');
      form.show();

      layer.bindPopup(form.prop('outerHTML')).openPopup();
      console.log('bound');
      console.log($('.georef-form'))
      $('.georef-form').submit(function(e) {
        console.log('hellwwo');
        e.preventDefault();
        return false;
      });

      console.log($('.georef-form'))
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
          // Create the div for the popup content
          popupContent = $('<div>');

          // Create the button for actually submitting it as georeferenced
          var button = $('<button>').addClass('btn btn-warning btn-sm').html('Set as georeferenced point');

          // Add the origin/georeferencing source
          popupContent.append($('<strong>').append(feature.properties.origin));
          button.attr('data-origin', feature.properties.origin);

          // Add the coordinates
          popupContent.append($('<br>'));
          popupContent.append(feature.geometry.coordinates[1] + ', ' + feature.geometry.coordinates[0]);
          button.attr('data-lat', feature.geometry.coordinates[1]);
          button.attr('data-long', feature.geometry.coordinates[0]);

          // TODO If it's saved in our database it has an id, so add that

          // Add the buffer if applicable
          if(feature.properties.buffer) {
              popupContent.append($('<br>'));
              popupContent.append('Resolution confidence: ' + feature.properties.buffer + 'm');
              button.attr('data-buffer', feature.properties.buffer);

              // TODO else they must set their own resolution confidence

              // Add the buffer to the map
              layer.on('click', function(e) {
                  L.circle([feature.geometry.coordinates[1], feature.geometry.coordinates[0]], feature.properties.buffer, {
                  'stroke': 0,
                  'fillColor': '#fff693'
                  }).addTo(map);
              });
          }
          else {
            popupContent.append('<br>Resolution confidence: <input type="text" placeholder="E.g. 500m"><br>');
          }

          // Create the click function for the button
          button.click(function() {
            /*var coords = $(this).attr('data-coordinates');
            var res = $(this).attr('data-resolution');
            var source = $(this).attr('data-source');
            var date = $(this).attr('data-date');*/
            console.log($(this).data());
            // Send info to get saved into the database
            $.ajax({
              url: georef_ajax_url,
              method: "POST",
              data: { 'content': $(this).data(), 'georeference_id': georeference_id, 'csrfmiddlewaretoken': csrf },
              dataType: "json"
            }).done(function(returned_data) {
              window.location = redirect_url;
            });
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