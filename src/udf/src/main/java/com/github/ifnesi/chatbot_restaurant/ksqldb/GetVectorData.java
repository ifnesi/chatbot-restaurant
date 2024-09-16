package com.github.ifnesi.chatbot_restaurant.ksqldb;

import io.confluent.ksql.function.udf.Udf;
import io.confluent.ksql.function.udf.UdfDescription;
import io.confluent.ksql.function.udf.UdfParameter;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpHeaders;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.nio.charset.StandardCharsets;

@UdfDescription(
    name = "GET_VECTOR_DATA",
    description = "Calls a REST API to generate embeddings from a given text input",
    author = "Italo Nesi",
    version = "1.0.0"
)
public class GetVectorData {

    @Udf(description = "Generate embeddings for a text by calling an external REST API")
    public String get_vector_data(
        @UdfParameter(value = "apiUrl", description = "URL for REST API service") final String apiUrl,
        @UdfParameter(value = "sentence", description = "Sentence to generate the vector data") final String sentence
    ) {

        JsonObject result = new JsonObject();

        try {
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(apiUrl))
                .header("Content-Type", "text/plain")
                .POST(HttpRequest.BodyPublishers.ofString(sentence == null? "" : sentence, StandardCharsets.UTF_8))
                .build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

            int statusCode = response.statusCode();
            String body = response.body();
            result = JsonParser.parseString(body == null? "{\"vector_data\": []}" : body).getAsJsonObject();
            result.addProperty("status_code", statusCode);
            result.addProperty("error", statusCode != 200);

        } catch (Exception e) {
            String message = e.getMessage();
            result.addProperty("status_code", 500);
            result.addProperty("error", true);
            result.addProperty("message", message == null? "Internal error" : message);
        }

        return result.toString();
    }
}
