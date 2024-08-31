CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE IF NOT EXISTS public.customer_profiles (
    id VARCHAR PRIMARY KEY,
    hashed_pwd VARCHAR,
    full_name VARCHAR,
    dob DATE,
    allergies VARCHAR
);
INSERT INTO public.customer_profiles (id, hashed_pwd, full_name, dob, allergies) VALUES
    ('wesley', crypt('wesley', '$ENV.MD5_PASSWORD_SALT'), 'Wesley Wheatworth', '1976/03/02', 'Gluten'),
    ('noah', crypt('noah', '$ENV.MD5_PASSWORD_SALT'), 'Noah Lergey', '1988/07/23', null),
    ('shelly', crypt('shelly', '$ENV.MD5_PASSWORD_SALT'), 'Shelly Cheesewright', '1966/04/22', 'Dairy, Eggs'),
    ('fernando', crypt('fernando', '$ENV.MD5_PASSWORD_SALT'), 'Fernando Fishfinn', '1955/01/19', 'Fish'),
    ('edward', crypt('edward', '$ENV.MD5_PASSWORD_SALT'), 'Edward Eggson', '1993/06/22', 'Eggs'),
    ('connor', crypt('connor', '$ENV.MD5_PASSWORD_SALT'), 'Connor Crabb', '2001/11/27', 'Shellfish'),
    ('james', crypt('james', '$ENV.MD5_PASSWORD_SALT'), 'James Young', '2012/09/30', null);