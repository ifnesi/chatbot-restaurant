package com.example.ksql;

import io.confluent.ksql.function.udf.Udf;
import io.confluent.ksql.function.udf.UdfDescription;
import io.confluent.ksql.function.udf.UdfParameter;

import org.apache.http.client.methods.HttpPost;
import org.apache.http.entity.StringEntity;
import org.apache.http.impl.client.CloseableHttpClient;
import org.apache.http.impl.client.HttpClients;
import org.apache.http.util.EntityUtils;

import java.nio.charset.StandardCharsets;

@UdfDescription(
    name = "GENERATE_EMBEDDING",
    description = "Calls a REST API to generate embeddings from a given text input",
    author = "Italo Nesi",
    version = "1.0.0"
)
public class Generate_Embedding {

    private static final String API_URL = "http://chatbot:9999/api/v1/embedding/sentence-transformer";

    @Udf(description = "Generate embeddings for a text by calling an external REST API")
    public String generate_embedding(
        @UdfParameter(value = "sentence", description = "Sentence") final String sentence
    ) {
        try (CloseableHttpClient client = HttpClients.createDefault()) {
            HttpPost request = new HttpPost(API_URL);
            request.setHeader("Content-Type", "text/plain");
            request.setEntity(new StringEntity(sentence, StandardCharsets.UTF_8));
            return EntityUtils.toString(client.execute(request).getEntity());
        } catch (Exception e) {
            throw new RuntimeException("Error calling GENERATE_EMBEDDING API", e);
        }
    }
}
