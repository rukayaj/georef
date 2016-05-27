dayValidator = function(value, callback) {
    callback(value <= 31 && value > -1);
};

monthValidator = function(value, callback) {
    callback(value <= 12 && value > -1);
};

yearValidator = function(value, callback) {
    this_year = new Date().getFullYear();
    callback((value <= this_year && value > 1500) || value == 0);
};

var hotSettings = {
    columns: [
        {
            data: 'brahms',
            type: 'numeric',
        },
        {
            data: 'collector_number',
            type: 'text'
        },
        {
            data: 'collected_day',
            type: 'numeric',
            validator: dayValidator
        },
        {
            data: 'collected_month',
            type: 'numeric',
            validator: monthValidator
        },
        {
            data: 'collected_year',
            type: 'numeric',
            validator: yearValidator
        },
        {
            data: 'latdec',
            type: 'numeric',
            format: '00.00000000',
        },
        {
            data: 'longdec',
            type: 'numeric',
            format: '00.00000000',
        },
        {
            data: 'llres',
            type: 'text',
        },
        {
            data: 'locality',
            type: 'text',
        }
    ],
    stretchH: 'all',
    autoWrapRow: true,
    height: 400,
    minRows: 2,
    rowHeaders: true,
    colHeaders: [
        'brahms',
        'collector_number',
        'collected_day',
        'collected_month',
        'collected_year',
        'latdec',
        'longdec',
        'llres',
        'locality'
    ]
};

var container = document.getElementById('hot');
var hot = new Handsontable(container, hotSettings);

$(document).ready(function() {
    // The georeferencing form must first be populated with the hot data before submitting
    $('form#process').submit(function(event) {
        // Sometimes it seems to get ahead of itself so prevent default
        event.preventDefault();
        var self = this;

        // Get the data in the cells
        var htData = hot.getData();

        // If the last row is empty, remove it before validation
        if(htData.length > 1 && hot.isEmptyRow(htData.length - 1)) {
            hot.alter('remove_row', parseInt(htData.length - 1), keepEmptyRows = false);
        }

        // Validate the cells and submit the form
        hot.validateCells(function(result, obj) {
            if(result == true) {
                // Populate hidden form input with the hot data, see http://www.rawrers.org/?p=890
                document.getElementById("data").value = JSON.stringify(htData);

                // Call default
                self.submit();

                // If it needs to get ajax in the future.... http://blog.merren.net/2013/02/django-ajax-post-and-csrf.html
                // $.ajax({ type: "POST", url:, dataType: 'json', async: false, data:, success: function () {}})
            }
            // If there are validation errors, do not allow them to submit
            else {
                alert('Invalid cells');
            }
        });
    });
});