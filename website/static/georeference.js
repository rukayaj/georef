$(document).ready(function() {
  // An easy hacky way to make the textarea smaller
  $('textarea').attr('rows', 3);

  // Enable tooltips
  $(function () {
    $('[data-toggle="tooltip"]').tooltip()
  })

  // Initialise map
  map = L.map('leaflet').setView([-29, 24.5], 5);
  var overlayMaps = {};
  var baseMaps = {};

  // Add the TOPO sheets layer - Should really be a tiledMapLayer but this does not seem to work...
  topo =  L.esri.dynamicMapLayer({
    url: 'http://bgismaps.sanbi.org/arcgis/rest/services/2016TopoSheets/MapServer',
    useCors: false
  });
  overlayMaps["Topo sheet"] = topo;

  // Add the boundaries layer
  boundaries =  L.esri.dynamicMapLayer({
    url: 'http://bgismaps.sanbi.org/arcgis/rest/services/Basedata_transport/MapServer',
    useCors: false
  });
  overlayMaps["Roads"] = boundaries;

  // If we've got collector points, add them in as a layer
  if(same_collector_points) {
    // Create a geojson layer, see https://www.dartdocs.org/documentation/leaflet/0.0.1-alpha.4/leaflet.layer/GeoJSON/addData.html
    collectorLayer = L.geoJson(same_collector_points, {
      pointToLayer: function(feature, latlng) { // Change marker according to input type
          marker = SameGroupMarker;
          return L.marker(latlng, {icon: SameGroupMarker});
      },
      onEachFeature: function (feature, layer) {
        popupContent = feature.properties.notes;
        // Bind the layer with the form
        layer.bindPopup(popupContent);
      }
    });
    overlayMaps['Places the collector went'] = collectorLayer;
  }

  // If it's been georeferenced, add that marker to its own special layer
  if(geographical_position) {
    var mainLayer;
    layer = L.geoJson(geographical_position, {
      pointToLayer: function(feature, latlng) {
        return L.marker(latlng, {icon: GeoreferencedMarker});
      },
      onEachFeature: function (feature, layer) {
        layer.bindPopup('&nbsp;');
        mainLayer = layer;
      }
    });
    //layer = L.marker(geographical_position, {icon: GeoreferencedMarker}).bindPopup('&nbsp;');

    // Populate the layer and get the form content
    layer.precision_m = geographical_position_precision_m;
    layer.g_author = author;
    layer.g_locality_name = locality_name;
    var form = getFormForPopup(layer);

    // Hide the buttons
    $(form).find('button').hide();

    // Set the popup content, could also just bind popup with this to start with, but too lazy to change it
    mainLayer._popup.setContent(form.prop('outerHTML'));

    // Add to the overlay maps
    GeoreferencedLayer = L.layerGroup([layer]);

    // Add to the map and zoom
    map.addLayer(layer);
    coords = getLayerCoords(layer);
    map.setView(coords, 10);
    overlayMaps['Georeferenced point'] = GeoreferencedLayer;
  }

  // Add the national geographic (relief map) and satellite layers layer
  baseMaps['National geographic'] = L.esri.basemapLayer('NationalGeographic');
  baseMaps["Satellite imagery"] = L.esri.basemapLayer('Imagery');

  // Add the default basemap layer
  base = L.tileLayer('http://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Map data &copy; 2013 OpenStreetMap contributors',
  });
  base.addTo(map);
  base.bringToFront();
  baseMaps["Default"] = base;

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

    // Insert an empty popup
    if (type === 'marker') {
      layer.bindPopup('&nbsp;').openPopup();
    }

    // Add to editable layers list
    editableLayers.addLayer(layer);

    // We have to add the popup content in after adding layer
    if (type === 'marker') {
      // Persist buffer value
      layer.precision_m = 1000;
      layer.g_author = 'User';
      layer.g_locality_name = 'User';
      var form = getFormForPopup(layer);
      layer._popup.setContent(form.prop('outerHTML'));
    }
  });

  // Add the measure control for areas
  var measureAreaControl = new L.control.measure();
  map.addControl(measureAreaControl);

  // Add the measure control for lines
  var measureControl = new L.Control.measureControl();
  map.addControl(measureControl);

  function getLayerCoords(layer) {
    if(typeof layer.getLatLng != 'undefined') {
      return layer.getLatLng();
    }
    else if(typeof layer.getBounds != 'undefined') {
      return layer.getBounds().getCenter();
    }
    return false;
  }

  function getFormForPopup(layer) {
    // Default
    popupContent = 'No information available.';

    // Make a copy of the template form (hidden in the HTML) and change the class and show it
    var form = $('.template-form').clone();
    form.removeClass('template-form');
    form.addClass('georef-form');
    form.addClass('pk-' + layer._leaflet_id);
    form.show();

    // Set the heading
    $(form).find('.form-heading').text(layer.g_locality_name);
    $(form).find('.form-origin').text(layer.g_author);


    // Determine if we are dealing with point or polygon and set coords accordingly
    coords = getLayerCoords(layer);
    if(coords) {
      $(form).find('.form-coords').text(coords.lat.toFixed(5) + ', ' + coords.lng.toFixed(5));
    }
    if(typeof layer.feature != 'undefined') {
      if(layer.feature.geometry.type == 'Polygon') {
        $(form).find('#id_point').val('SRID=4326;POLYGON (' + coords.lng + ' ' + coords.lat + ')');
      }
      else {
        $(form).find('#id_point').val('SRID=4326;POINT (' + coords.lng + ' ' + coords.lat + ')');
      }

      // Add georef pk to post if possible
      $(form).attr('action', (form).attr('action') + layer.feature.properties.pk)
    }

    // Add precision
    $(form).find('input[name="precision_m"]').val(layer.precision_m);
    $(form).find('input[name="precision_m"]').attr('value', layer.precision_m);
    $(form).find('input[name="precision_m"]').attr('readonly', true);

    // Correct the delete url, or hide it
    deleteUrl = $(form).find('.delete-prompt').attr('data-url').replace('0', layer._leaflet_id);
    $(form).find('.delete-prompt').attr('data-url', deleteUrl);

    return form;
  }

  // Create a geojson layer, see https://www.dartdocs.org/documentation/leaflet/0.0.1-alpha.4/leaflet.layer/GeoJSON/addData.html
  geojsonLayer = L.geoJson(potential_geographical_positions, {
    pointToLayer: function(feature, latlng) { // Change marker according to input type
      return L.marker(latlng, {icon: getMarker(feature.properties.author)}); // L.CircleMarker(latlng, {radius: 10, fillOpacity: 0.85});
    },
    onEachFeature: function (feature, layer) {
      if(feature.geometry && feature.properties) {
          // We have to set precision_m as a layer property, feature properties don't seem to persist
          if($.isNumeric(feature.properties.precision_m)){
            layer.precision_m = parseInt(feature.properties.precision_m, 10)
          }

          // Set a unique id... Leaflet does automatically generate one but for some reason can't access it, so setting it to pk
          // Easiest to pass around the variables as a layer's property as when the user manually puts in a marker it doesn't seem to be a feature
          layer._leaflet_id = feature.properties.pk;
          layer.g_author = feature.properties.author;
          layer.g_locality_name = feature.properties.locality_name;

          // Get the form content
          form = getFormForPopup(layer);

          // Bind the layer with the form
          layer.bindPopup(form.prop('outerHTML'));

          // Add to list
          item = '<tr><td>' + feature.properties.locality_name + '</td><td>' + feature.properties.author +
          '</td><td><button class="btn btn-default pan-button" data-leaflet-id="' + feature.properties.pk + '">Pan</button></td></tr>';
          $('#places > tbody:last-child').append(item);
      }
    }
  });

  if(geographical_position) {
  }
  else {
    // Add the layer to the map and zoom to it
    map.addLayer(geojsonLayer);
    map.fitBounds(geojsonLayer, {padding: [80, 80]});
  }
  overlayMaps['Potential georeferences'] = geojsonLayer;

  // Add baselayers and overlayers
  L.control.layers(baseMaps, overlayMaps).addTo(map);

  // When clicking on a list item, make the map pan to that locality point + open popup
  $('.pan-button').click(function () {
    marker_id = this.getAttribute('data-leaflet-id');
    layer = geojsonLayer.getLayer(marker_id);

    // Determine if we are dealing with point or polygon and set coords accordingly
    coords = getLayerCoords(layer);

    // If we have some coords, zoom to it, open popup and scroll user up to map
    if(typeof coords != 'undefined') {
      map.panTo(coords);
      map.zoomIn(2);
    }
    layer.openPopup();
    $('html,body').animate({ scrollTop: $('#leaflet').offset().top}, 'fast');
  });

  // Add buffer when popup opens
  var bufferStyle = {'stroke': 0, 'fillColor': '#fff693'};
  var circle;
  map.on('popupopen', function(e) {
    var layer = e.popup._source;
    if(layer.precision_m > 0) {
      // Add buffer to map as circle
      circle = new L.CircleEditor(layer.getLatLng(), layer.precision_m);
      circle.addTo(map);

      // When editing circle, update the form precision_m + the layer precision_m property
      circle.on('edit', function(){
          var form = $('.pk-' + layer._leaflet_id);
          form.find('input[name="precision_m"]').attr('value', Math.round(this.getRadius()));
          form.find('input[name="precision_m"]').val(Math.round(this.getRadius()));
          layer.precision_m = Math.round(this.getRadius());
      });
    }
  });

  // When popup closes
  map.on('popupclose', function(e) {
    var layer = e.popup._source;
    if(layer.precision_m > 0) {
      // Remove buffer circle
      map.removeLayer(circle);

      // Persist buffer value
      var newForm = getFormForPopup(layer);
      layer._popup.setContent(newForm.prop('outerHTML'));
    }
  });

  // Make datatables work
  $('#places').DataTable();
});