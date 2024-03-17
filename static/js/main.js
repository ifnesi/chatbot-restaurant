$( document ).ready(function() {
    $("#customerMessage").on('keyup', function (event) {
        if (event.keyCode === 13) {
            send_message(0);
        }
    });
    send_message(1);
});


function send_message(initial) {
    var customerMessage = $("#customerMessage").val();
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
            var chat_history = "";
            $("#customerMessage").val("");
            $("#customerMessage").focus();
            if (data.customer)
                chat_history += '<p><img src="/static/images/customer.png" class="p-1" height="28px"></img><span class="badge bg-warning text-dark">' + data.customerName + '</span></br>' + data.customer + '</p>';
            if (data.waiter)
                chat_history += '<p><img src="/static/images/waiter.png" class="p-1" height="28px"></img><span class="badge bg-primary text-light">' + data.waiterName + '</span></br>' + data.waiter + '</p>';
            $("#chat-history").append(chat_history);
            var textarea = document.getElementById("chat-history");
            textarea.scrollTop = textarea.scrollHeight;
        }
  });
}