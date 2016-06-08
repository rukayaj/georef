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

var headings = [
        'unique_id',
        'group',
        'day',
        'month',
        'year',
        'lat',
        'long',
        'res',
        'locality'
    ]
var hotSettings = {
    columns: [
        {
            data: headings[0],
            type: 'numeric',
        },
        {
            data: headings[1],
            type: 'text'
        },
        {
            data: headings[2],
            type: 'numeric',
            validator: dayValidator
        },
        {
            data: headings[3],
            type: 'numeric',
            validator: monthValidator
        },
        {
            data: headings[4],
            type: 'numeric',
            validator: yearValidator
        },
        {
            data: headings[5],
            type: 'numeric',
            format: '00.00000000',
        },
        {
            data: headings[6],
            type: 'numeric',
            format: '00.00000000',
        },
        {
            data: headings[7],
            type: 'text',
        },
        {
            data: headings[8],
            type: 'text',
        }
    ],
    stretchH: 'all',
    autoWrapRow: true,
    height: 400,
    minRows: 2,
    rowHeaders: true,
    colHeaders: headings
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