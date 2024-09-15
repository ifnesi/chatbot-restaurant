package com.example.ksql;

import io.confluent.ksql.function.udf.Udf;
import io.confluent.ksql.function.udf.UdfDescription;
import io.confluent.ksql.function.udf.UdfParameter;

import org.apache.http.client.methods.CloseableHttpResponse;
import org.apache.http.client.methods.HttpPost;
import org.apache.http.entity.StringEntity;
import org.apache.http.impl.client.CloseableHttpClient;
import org.apache.http.impl.client.HttpClients;
import org.apache.http.util.EntityUtils;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

@UdfDescription(
    name = "GENERATE_EMBEDDING",
    description = "Calls a REST API to generate embeddings from a given text input",
    author = "Italo Nesi",
    version = "1.0"
)
public class Generate_Embedding {

    private static final String API_URL = "http://chatbot:9999/api/v1/embedding/sentence-transformer";

    @Udf(description = "Generate embeddings for a text by calling an external REST API")
    public String generate_embedding(
        @UdfParameter(value = "sentence", description = "Sentence") final String sentence
    ) {

        try (CloseableHttpClient httpClient = HttpClients.custom()
            .setConnectionTimeToLive(10, TimeUnit.SECONDS)
            .build())
        {

            // Create the POST request
            HttpPost request = new HttpPost(API_URL);
            request.setHeader("Content-Type", "text/plain");

            // Set the request body (input text)
            StringEntity entity = new StringEntity(sentence, StandardCharsets.UTF_8);
            request.setEntity(entity);

            // Execute the POST request
            try (CloseableHttpResponse response = httpClient.execute(request)) {
                String responseBody = EntityUtils.toString(response.getEntity(), StandardCharsets.UTF_8);

                // Return the full JSON response
                return responseBody;
            }

        } catch (Exception e) {
            e.printStackTrace();
            throw new RuntimeException("Error calling embedding API", e);
        }
    }
}
