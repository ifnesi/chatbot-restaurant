$( document ).ready(function() {
    get_logs();
});

function get_logs() {
    $.ajax({
        type: "GET",
        url: "/get-logs",
        success: function(data) {
            $("#logs").append(data);
            setTimeout(function() {
                get_logs();
            }, 500);
        }
    });
}
