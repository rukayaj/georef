function getMarker(author_name) {
  switch(author_name) {
    case 'Google':
      marker = new L.ExtraMarkers.icon({
        icon: 'glyphicon glyphicon-leaf',
        markerColor: 'red',
        shape: 'square',
      });;
      break;
    case 'SameGroup':
      marker = new L.ExtraMarkers.icon({
        icon: 'glyphicon glyphicon-glass',
        markerColor: 'purple',
        shape: 'penta',
      });;
      break;
    case 'SABCA':
      marker = new L.ExtraMarkers.icon({
        icon: 'glyphicon glyphicon-cd',
        markerColor: 'orange',
        shape: 'square',
      });;
      break;
    case 'BRAHMS':
      marker = new L.ExtraMarkers.icon({
        icon: 'glyphicon glyphicon-music',
        markerColor: 'green',
        shape: 'square',
      });;
      break;
    case 'OpenStreetMap':
      marker = new L.ExtraMarkers.icon({
        icon: 'glyphicon glyphicon-fire',
        markerColor: 'orange-dark',
        shape: 'square',
      });
      break;
    case 'SANBI Gazetteer':
      marker = new L.ExtraMarkers.icon({
        icon: 'glyphicon glyphicon-fire',
        markerColor: 'black',
        shape: 'square',
      });;
      break;
    case 'Input':
      marker = new L.ExtraMarkers.icon({
        icon: 'glyphicon glyphicon-user',
        markerColor: 'green',
        shape: 'star',
      });;
      break;
    default:
      marker = new L.ExtraMarkers.icon({
        icon: 'glyphicon glyphicon-question-sign',
        markerColor: 'blue',
        shape: 'square',
      });;
  }
  return marker;
}
var GeoreferencedMarker = new L.ExtraMarkers.icon({
  icon: 'glyphicon glyphicon-ok',
  markerColor: 'green-light',
  shape: 'star',
});