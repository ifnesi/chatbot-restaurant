var waiterName;
var customerName;

$( document ).ready(function() {
    // Alert when trying to leave/refresh
    //$(window).on("unload", reaload_alert());

    // Bind ENTER to message box
    $("#customerMessage").on('keyup', function (event) {
        if (event.keyCode === 13) {
            send_message(0);
        }
    });
    
    // Send initial message
    waiterName = $("#waiterName").val();
    customerName = $("#customerName").val();
    send_message(1);
});

function reaload_alert() {
    var leave = confirm("Are you sure you want to leave? The chat history might be lost.");
    if (!leave)
        return null;
}

function send_message(initial) {
    var spanID = "_id-" + parseInt((new Date()).getTime()) + parseInt(Math.random() * 10000);
    var chat_history= '<p><img src="/static/images/customer.png" class="p-1" height="28px"></img><span class="badge bg-primary text-light">' + waiterName + '</span></br><span id="' + spanID + '"><span class="typing">Typing...</span></span></p>';
    var customerMessage = $("#customerMessage").val();
    if (customerMessage && initial == 0) {
        $("#customerMessage").val("");
        chat_history = '<p><img src="/static/images/customer.png" class="p-1" height="28px"></img><span class="badge bg-warning text-dark">' + customerName + '</span></br>' + customerMessage + '</p>' + chat_history;
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
            initialMessage: initial,
            customerMessage: customerMessage
        }),
        success: function(data) {
            $("#customerMessage").focus();
            $("#" + spanID).html(data.waiter);
        }
    });
}