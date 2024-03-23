var waiter_name;
var customer_name;

$( document ).ready(function() {
    // Alert when trying to leave/refresh
    $(window).bind('beforeunload', function(){
        return 'Are you sure you want to leave?';
      });

    // Bind ENTER to message box
    $("#customer_message").on('keydown', function (event) {
        if (event.keyCode === 13) {
            send_message(0);
        }
    });
    
    // Send initial message
    waiter_name = $("#waiter_name").val();
    customer_name = $("#customer_name").val();
    send_message(1);
});

function send_message(initial, message, wait_prompt) {
    wait_prompt = wait_prompt || "AI assistant is typing...";
    var chat_history = "";
    var customer_message = $("#customer_message").val();
    if (message !== undefined) {
        customer_message = message;
    }
    else if (customer_message && initial == 0) {
        $("#customer_message").val("");
        chat_history = '<img src="/static/images/customer.png" class="p-1" height="30px"></img><span class="badge bg-warning text-dark">' + customer_name + '</span><span class="message text-light">' + current_time() + '</span><div class="customer message mt-1 mb-1">' + customer_message + '</div>';
    }
    
    if (customer_message || initial > 0) {
        var spanID = "_id-" + parseInt((new Date()).getTime()) + parseInt(Math.random() * 10000);
        chat_history += '<img src="/static/images/waiter.png" class="p-1" height="30px"></img><span class="badge bg-primary text-light">' + waiter_name + '</span><span id="time' + spanID + '" class="message text-light">...</span><div id="' + spanID + '" class="chatbot message mt-1 mb-1"><span class="typing blink">' + wait_prompt + '</span></div>';

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
                customer_message: customer_message,
                span_id: spanID,
            }),
            success: function(data) {
                $("#customer_message").focus();
                $("#" + data.span_id).html(data.waiter);
                $("#time" + data.span_id).html(current_time());
            }
        });
    }
}

function main_menu(section) {
    send_message(0, "Show the " + section + " on the main menu in HTML format, make sure to highlight the allergies according to the customer profile and alcoholic restrictions based on their age", "Getting you the " + section.replaceAll("_", " ") + " on the main menu...");
}

function kids_menu(section) {
    send_message(0, "Show the " + section + " on kids menu in HTML format, make sure to highlight the allergies according to the customer profile", "Getting you the " + section.replaceAll("_", " ") + " on the kids menu...");
}

function my_bill() {
    send_message(0, "Show the current bill in HTML format, make sure to apply the service tax and discount if applicable", "Preparing your bill...");
}

function current_time() {
    var d = new Date()
    hours = format_two_digits(d.getHours());
    minutes = format_two_digits(d.getMinutes());
    seconds = format_two_digits(d.getSeconds());
    return hours + ":" + minutes + ":" + seconds;
}

function format_two_digits(n) {
    return n < 10 ? '0' + n : n;
}