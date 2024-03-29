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

function send_message(initial, context, query, wait_prompt) {
    context = context || "";
    wait_prompt = wait_prompt || "AI assistant is typing...";
    var chat_history = "";
    var customer_message = $("#customer_message").val();

    if (query !== undefined) {
        customer_message = query;
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
                context: context,
                query: customer_message,
                span_id: spanID,
            }),
            success: function(data) {
                $("#customer_message").focus();
                $("#total_tokens").html(data.total_tokens == -1? "N/A" : data.total_tokens);
                $("#" + data.span_id).html(data.waiter);
                $("#time" + data.span_id).html(current_time());
            }
        });
    }
}

function main_menu(section) {
    var context = "New customer message, response must be in HTML format, make sure to highlight the allergies and alcoholic restrictions according to the customer profile";
    var query = "Show me the " + section + " on the main menu";
    var wait_prompt = "Getting you the " + section.replaceAll("_", " ") + " on the main menu...";
    send_message(0, context, query, wait_prompt);
}

function kids_menu(section) {
    var context = "New customer message, response must be in HTML format, make sure to highlight the allergies and alcoholic restrictions according to the customer profile";
    var query = "Show me the " + section + " on the kids menu";
    var wait_prompt = "Getting you the " + section.replaceAll("_", " ") + " on the kids menu...";
    send_message(0, context, query, wait_prompt);
}

function my_bill() {
    var context = "New customer message, response must be in HTML format, make sure to apply the service tax and discount as per restaurant policies";
    var query = "Show me my current bill";
    var wait_prompt = "Checking on your bill...";
    send_message(0, context, query, wait_prompt);
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