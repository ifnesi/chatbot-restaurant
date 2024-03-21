var waiter_name;
var customer_name;

$( document ).ready(function() {
    // Alert when trying to leave/refresh
    //$(window).on("unload", reaload_alert());

    // Bind ENTER to message box
    $("#customer_message").on('keyup', function (event) {
        if (event.keyCode === 13) {
            send_message(0);
        }
    });
    
    // Send initial message
    waiter_name = $("#waiter_name").val();
    customer_name = $("#customer_name").val();
    send_message(1);
});

function reaload_alert() {
    var leave = confirm("Are you sure you want to leave? The chat history might be lost.");
    if (!leave)
        return null;
}

function send_message(initial) {
    var spanID = "_id-" + parseInt((new Date()).getTime()) + parseInt(Math.random() * 10000);
    var chat_history= '<p><img src="/static/images/customer.png" class="p-1" height="28px"></img><span class="badge bg-primary text-light">' + waiter_name + '</span></br><span id="' + spanID + '"><span class="typing blink">Typing...</span></span></p>';
    var customer_message = $("#customer_message").val();
    if (customer_message && initial == 0) {
        $("#customer_message").val("");
        chat_history = '<p><img src="/static/images/customer.png" class="p-1" height="28px"></img><span class="badge bg-warning text-dark">' + customer_name + '</span></br>' + customer_message + '</p>' + chat_history;
    }
    $("#chat-history").append(chat_history);
    var textarea = document.getElementById("chat-history");
    textarea.scrollTop = textarea.scrollHeight;

    // POST question to B/E
    $.ajax({
        type: "POST",
        url: "/send-message",
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        data: JSON.stringify({
            initial_message: initial,
            customer_message: customer_message
        }),
        success: function(data) {
            $("#customer_message").focus();
            $("#" + spanID).html(data.waiter);
        }
    });
}