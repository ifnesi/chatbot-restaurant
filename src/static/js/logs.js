$( document ).ready(function() {
    get_logs();
});

function get_logs() {
    $.ajax({
        type: "GET",
        url: "/get-logs",
        async: false,
        success: function(data) {
            if (data)
                $("#logs").append(data);
            setTimeout(function() {
                get_logs();
            }, 500);
        }
    });
}
