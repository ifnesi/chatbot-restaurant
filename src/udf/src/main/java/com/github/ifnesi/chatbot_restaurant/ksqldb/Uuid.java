package com.github.ifnesi.chatbot_restaurant.ksqldb;

import io.confluent.ksql.function.udf.Udf;
import io.confluent.ksql.function.udf.UdfDescription;
import io.confluent.ksql.function.udf.UdfParameter;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

@UdfDescription(
    name = "HASH_MD5",
    description = "Hash String using MD5 and return in UUID format",
    author = "Italo Nesi",
    version = "1.0.0"
)
public class Uuid {

    @Udf(description = "Hash String using MD5 and return in UUID format")
    public String hash_md5(
        @UdfParameter(value = "text", description = "String to be hashed") final String text
    ) {
        try {
            MessageDigest md = MessageDigest.getInstance("MD5");
            byte[] messageDigest = md.digest(text.getBytes());
            StringBuilder hexString = new StringBuilder();
            for (byte b : messageDigest) {
                String hex = Integer.toHexString(0xff & b);
                if (hex.length() == 1) hexString.append('0');
                hexString.append(hex);
            }
            String md5Hash = hexString.toString();
            return md5Hash.substring(0, 8) + "-" +
                md5Hash.substring(8, 12) + "-" +
                md5Hash.substring(12, 16) + "-" +
                md5Hash.substring(16, 20) + "-" +
                md5Hash.substring(20);
        } catch (NoSuchAlgorithmException e) {
            throw new RuntimeException(e);
        }
    }
}
